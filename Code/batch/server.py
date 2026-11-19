"""HTTP serving layer for one bounded T4 batch worker."""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import os
import queue
import threading
import time
import wave
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field


class QueueFull(Exception):
    pass


@dataclass
class Job:
    texts: list[str]
    max_frames: int | None
    profile_id: str | None = None
    on_chunk: Callable[..., None] | None = None
    future: Future = field(default_factory=Future)
    stop: threading.Event = field(default_factory=threading.Event)
    cancelled: bool = False
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    first_chunk_at: float | None = None


@dataclass
class Settings:
    max_batch: int = 192
    max_queue: int = 256
    max_rows: int = 224
    max_frames: int = 192
    timeout_s: float = 30.0
    max_texts: int = 32
    max_chars: int = 4000
    sample_rate: int = 24000


class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.accepted = 0
        self.rejected = 0
        self.completed = 0
        self.failed = 0
        self.cancelled = 0
        self.slow_clients = 0
        self.last_errors: list[str] = []
        self.queue_ms: list[float] = []
        self.first_ms: list[float] = []
        self.total_ms: list[float] = []

    def add(self, name: str, value: int = 1) -> None:
        with self.lock:
            setattr(self, name, getattr(self, name) + value)

    def add_error(self, message: str) -> None:
        with self.lock:
            self.last_errors.append(message)
            del self.last_errors[:-20]

    @staticmethod
    def _stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "max": 0.0}
        data = sorted(values)
        return {
            "count": len(data),
            "p50": round(data[len(data) // 2], 2),
            "p95": round(data[min(len(data) - 1, int(len(data) * 0.95))], 2),
            "max": round(data[-1], 2),
        }

    def record(self, queue_ms: float, first_ms: float | None, total_ms: float) -> None:
        with self.lock:
            self.queue_ms.append(queue_ms)
            if first_ms is not None:
                self.first_ms.append(first_ms)
            self.total_ms.append(total_ms)
            for items in (self.queue_ms, self.first_ms, self.total_ms):
                del items[:-1000]

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "completed": self.completed,
                "failed": self.failed,
                "cancelled": self.cancelled,
                "slow_clients": self.slow_clients,
                "last_errors": self.last_errors[-5:],
                "queue_ms": self._stats(self.queue_ms),
                "first_chunk_ms": self._stats(self.first_ms),
                "total_ms": self._stats(self.total_ms),
            }


class BatchWorker:
    def __init__(
        self,
        engine: Any,
        max_batch: int,
        max_queue: int,
        max_rows: int,
        metrics: Metrics,
    ) -> None:
        self.engine = engine
        self.max_batch = max_batch
        self.max_rows = max_rows
        self.metrics = metrics
        self.jobs: queue.Queue[Job] = queue.Queue(maxsize=max_queue)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def depth(self) -> int:
        return self.jobs.qsize()

    def submit(
        self,
        texts: list[str],
        max_frames: int | None,
        profile_id: str | None = None,
        on_chunk: Callable[..., None] | None = None,
    ) -> Job:
        job = Job(
            texts=texts,
            max_frames=max_frames,
            profile_id=profile_id,
            on_chunk=on_chunk,
        )
        if len(texts) > self.max_rows:
            self.metrics.add("rejected")
            raise QueueFull("too many rows")
        try:
            self.jobs.put_nowait(job)
        except queue.Full as exc:
            self.metrics.add("rejected")
            raise QueueFull("queue is full") from exc
        self.metrics.add("accepted")
        return job

    def _run(self) -> None:
        while True:
            job = self.jobs.get()
            batch = [job]
            rows = len(job.texts)
            deadline = time.monotonic() + float(os.getenv("ARSENAL_BATCH_WINDOW_MS", "100")) / 1000.0
            while len(batch) < self.max_batch and rows < self.max_rows:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    nxt = self.jobs.get(timeout=remaining)
                except queue.Empty:
                    break
                if nxt.cancelled:
                    nxt.future.set_exception(asyncio.CancelledError())
                    self.metrics.add("cancelled")
                    continue
                if rows + len(nxt.texts) > self.max_rows:
                    self.jobs.put_nowait(nxt)
                    break
                batch.append(nxt)
                rows += len(nxt.texts)
            self._execute(batch)

    def _group_key(self, job: Job) -> str | None:
        return None

    def _execute(self, batch: list[Job]) -> None:
        active = [job for job in batch if not job.cancelled]
        for job in batch:
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
        if not active:
            return
        groups: dict[str | None, list[Job]] = {}
        for job in active:
            groups.setdefault(self._group_key(job), []).append(job)
        for profile_id, jobs in groups.items():
            self._execute_group(jobs, profile_id)

    def _execute_group(self, jobs: list[Job], profile_id: str | None) -> None:
        texts = [text for job in jobs for text in job.texts]
        owners = [job for job in jobs for _ in job.texts]
        frames = [job.max_frames for job in jobs]
        max_frames = None if any(f is None for f in frames) else max(frames)
        stop = jobs[0].stop if len(jobs) == 1 else None
        for job in jobs:
            job.started_at = time.monotonic()

        def relay(row: int, frame: Any, elapsed: float) -> None:
            job = owners[row]
            now = time.monotonic()
            if job.first_chunk_at is None:
                job.first_chunk_at = now
            if job.on_chunk is not None:
                job.on_chunk(frame, elapsed)

        try:
            profile_ids = [
                job.profile_id for job in jobs for _ in job.texts
            ]
            audio = self.engine.synthesize(
                texts,
                max_frames=max_frames,
                stop=stop,
                profile_id=profile_id,
                profile_ids=profile_ids,
                on_chunk=relay,
            )
        except Exception as exc:
            self.metrics.add("failed")
            self.metrics.add_error(str(exc))
            for job in jobs:
                if not job.future.done():
                    job.future.set_exception(exc)
            return
        offset = 0
        for job in jobs:
            count = len(job.texts)
            part = audio[offset : offset + count]
            offset += count
            now = time.monotonic()
            started = job.started_at or now
            first = None
            if job.first_chunk_at is not None:
                first = (job.first_chunk_at - job.created_at) * 1000.0
            self.metrics.record(
                (started - job.created_at) * 1000.0, first, (now - job.created_at) * 1000.0
            )
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
            else:
                job.future.set_result(part)
                self.metrics.add("completed")


def concat_audio(parts: list[Any]) -> Any:
    if len(parts) == 1:
        return parts[0]
    import numpy as np

    arrays = []
    for part in parts:
        if hasattr(part, "detach"):
            part = part.detach().float().cpu().numpy()
        arrays.append(np.asarray(part, dtype="float32"))
    return np.concatenate(arrays)


def pcm_bytes(samples: Any) -> bytes:
    if hasattr(samples, "detach"):
        samples = samples.detach().float().cpu().numpy()
    import numpy as np

    data = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    return (data * 32767.0).astype("<i2").tobytes()


def wav_bytes(samples: Any, sample_rate: int) -> bytes:
    if hasattr(samples, "detach"):
        samples = samples.detach().float().cpu().numpy()
    import numpy as np

    data = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buf.getvalue()


class TTSEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stream = None
        self.model = None
        self.profiles: dict[str, str] = {}
        self.profile_streams: dict[str, Any] = {}
        self.fallback_streams: dict[Any, Any] = {}
        self.mixed_stream: Any = None
        self.profile_voices: dict[str, Any] = {}
        self.default_is_profile = False
        self.prewarm_ms = 0.0
        self.ready = False

    def load(self) -> None:
        import logging
        import sys
        from pathlib import Path

        import torch

        code_root = Path(__file__).resolve().parents[1]
        model_dir = Path(os.getenv("ARSENAL_MODEL_DIR", code_root / "model"))
        sys.path.insert(0, str(code_root))
        extra = os.getenv("ARSENAL_POCKET_TTS")
        if extra:
            sys.path.insert(0, extra)
        old = os.getcwd()
        os.chdir(model_dir)
        logging.disable(logging.CRITICAL)
        try:
            from pocket_tts import TTSModel

            from batch.batched_stream import BatchedStream
            from batch.fp16 import enable_fp16_backbone
            from batch.fp16_weights import load_fp16_weights

            model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
            enable_fp16_backbone(model, mimi_fp16=True)
            weights = Path("fp16_weights.pt")
            if weights.exists():
                load_fp16_weights(model, weights)
            kwargs: dict[str, Any] = {
                "model": model,
                "max_first_tokens": int(os.getenv("ARSENAL_FIRST_TOKENS", "16")),
                "max_allowed_frames": int(os.getenv("ARSENAL_MAX_FRAMES", "192")),
            }
            profile = os.getenv("ARSENAL_VOICE_PROFILE")
            if profile:
                kwargs["voice_profile"] = profile
            else:
                voice = os.getenv(
                    "ARSENAL_VOICE",
                    str(code_root / "probes" / "ref" / "voice.wav"),
                )
                kwargs["voice"] = voice
                kwargs["voice_seconds"] = float(os.getenv("ARSENAL_VOICE_SECONDS", "4.0"))
            self.stream = BatchedStream(**kwargs)
            self.stream.stream(["Ready."], max_frames=1)
            self.model = model
            self._cls = BatchedStream
            self.default_is_profile = bool(profile)
            raw = os.getenv("ARSENAL_VOICE_PROFILES", "")
            for part in raw.replace(",", ";").split(";"):
                if "=" not in part:
                    continue
                name, path = part.split("=", 1)
                if name.strip() and path.strip():
                    self.profiles[name.strip()] = path.strip()
            from batch.boot import maybe_prewarm

            n = int(os.getenv("ARSENAL_PREWARM_B", "192"))
            self.prewarm_ms = maybe_prewarm(self.stream, ["Ready."] * max(1, n))
            torch.cuda.synchronize()
            self.ready = True
        finally:
            os.chdir(old)

    def has_profile(self, profile_id: str) -> bool:
        import os as _os

        path = self.profiles.get(profile_id)
        return bool(path and _os.path.exists(path))

    def _profile_stream(self, profile_id: str) -> Any:
        if not self.has_profile(profile_id):
            raise ValueError(f"unknown voice profile {profile_id!r}")
        stream = self.profile_streams.get(profile_id)
        if stream is None:
            stream = self._cls(
                self.model,
                voice_profile=self.profiles[profile_id],
                max_first_tokens=int(os.getenv("ARSENAL_FIRST_TOKENS", "16")),
                max_allowed_frames=int(os.getenv("ARSENAL_MAX_FRAMES", "192")),
            )
            self.profile_streams[profile_id] = stream
        return stream

    def _stream_for(self, profile_id: str | None) -> Any:
        if profile_id is None:
            return self.stream
        return self._profile_stream(profile_id)

    def _normal_stream(self, profile_id: str | None) -> Any:
        key = ("default",) if profile_id is None else profile_id
        stream = self.fallback_streams.get(key)
        if stream is None:
            source = self._stream_for(profile_id)
            stream = copy.copy(source)
            stream.voice_state = None
            stream._ids_cache = dict(source._ids_cache)
            stream.last_truncated_rows = []
            self.fallback_streams[key] = stream
        return stream

    def _profile_voice(self, profile_id: str) -> Any:
        voice = self.profile_voices.get(profile_id)
        if voice is None:
            import torch

            data = torch.load(self.profiles[profile_id], map_location="cpu")
            voice = data["voice_emb"][0].to(self.stream.voice.device)
            self.profile_voices[profile_id] = voice
        return voice

    def _mixed_stream(self) -> Any:
        if self.mixed_stream is None:
            self.mixed_stream = self._cls(
                self.model,
                voices=[],
                max_first_tokens=int(os.getenv("ARSENAL_FIRST_TOKENS", "16")),
                max_allowed_frames=int(os.getenv("ARSENAL_MAX_FRAMES", "192")),
            )
        return self.mixed_stream

    def chunks_for(self, text: str, profile_id: str | None = None) -> list[str]:
        if self.stream is None:
            raise RuntimeError("engine is not loaded")
        return self._stream_for(profile_id)._text_chunks(text)

    def batch_key(self, text: str, profile_id: str | None = None) -> Any:
        conditioned = profile_id is not None or self.default_is_profile
        if not conditioned:
            return None
        stream = self._stream_for(profile_id)
        first = stream._text_chunks(text)[0]
        return len(stream._text_ids(first))

    def synthesize(
        self,
        texts: list[str],
        max_frames: int | None = None,
        stop: Any = None,
        profile_id: str | None = None,
        profile_ids: list[str | None] | None = None,
        on_chunk: Callable[..., None] | None = None,
    ) -> list[Any]:
        if self.stream is None:
            raise RuntimeError("engine is not loaded")
        if profile_ids is not None and len(set(profile_ids)) > 1:
            stream = self._mixed_stream()
            stream.voices = [
                self._profile_voice(pid) if pid is not None else self.stream.voice[0]
                for pid in profile_ids
            ]
            return stream.stream(
                texts, max_frames=max_frames, stop=stop, on_chunk=on_chunk
            )
        stream = self._stream_for(profile_id)
        conditioned = profile_id is not None or self.default_is_profile
        if conditioned and len(texts) > 1:
            keys = {self.batch_key(text, profile_id) for text in texts}
            if len(keys) > 1:
                stream = self._normal_stream(profile_id)
        return stream.stream(
            texts, max_frames=max_frames, stop=stop, on_chunk=on_chunk
        )


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    max_frames: int | None = Field(default=None, ge=1)
    voice_profile: str | None = None


class BatchRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    max_frames: int | None = Field(default=None, ge=1)
    voice_profile: str | None = None


def create_app(
    engine: Any | None = None,
    settings: Settings | None = None,
    start_engine: bool = True,
) -> FastAPI:
    settings = settings or Settings(
        max_batch=int(os.getenv("ARSENAL_MAX_BATCH", "192")),
        max_queue=int(os.getenv("ARSENAL_MAX_QUEUE", "256")),
        max_rows=int(os.getenv("ARSENAL_MAX_ROWS", "224")),
        max_frames=int(os.getenv("ARSENAL_MAX_FRAMES", "192")),
        timeout_s=float(os.getenv("ARSENAL_TIMEOUT_S", "30")),
        max_texts=int(os.getenv("ARSENAL_MAX_TEXTS", "32")),
        max_chars=int(os.getenv("ARSENAL_MAX_CHARS", "4000")),
        sample_rate=int(os.getenv("ARSENAL_SAMPLE_RATE", "24000")),
    )
    metrics = Metrics()
    engine = engine or TTSEngine(settings)
    worker = BatchWorker(
        engine, settings.max_batch, settings.max_queue, settings.max_rows, metrics
    )
    app = FastAPI(title="arsenal-tts")
    app.state.engine = engine
    app.state.worker = worker
    app.state.metrics = metrics
    app.state.settings = settings
    app.state.start_engine = start_engine

    @app.on_event("startup")
    def load_engine() -> None:
        if app.state.start_engine and hasattr(engine, "load"):
            try:
                engine.load()
            except Exception:
                engine.ready = False

    def validate(
        texts: list[str], profile_id: str | None = None, max_frames: int | None = None
    ) -> None:
        if len(texts) > settings.max_texts:
            raise HTTPException(status_code=413, detail="too many texts")
        for text in texts:
            if not text.strip():
                raise HTTPException(status_code=422, detail="empty text")
            if len(text) > settings.max_chars:
                raise HTTPException(status_code=413, detail="text is too long")
        if max_frames is not None and max_frames > settings.max_frames:
            raise HTTPException(status_code=413, detail="max_frames is too large")
        if profile_id is not None:
            if not getattr(engine, "has_profile", lambda _: False)(profile_id):
                raise HTTPException(status_code=400, detail="unknown voice profile")

    async def wait_for(job: Job, request: Request) -> list[Any]:
        wrapped = asyncio.wrap_future(job.future)
        deadline = time.monotonic() + settings.timeout_s
        while True:
            if await request.is_disconnected():
                job.cancelled = True
                job.stop.set()
                metrics.add("cancelled")
                raise HTTPException(status_code=499, detail="client disconnected")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                job.cancelled = True
                job.stop.set()
                metrics.add("cancelled")
                raise HTTPException(status_code=504, detail="request timed out")
            done, _ = await asyncio.wait({wrapped}, timeout=min(0.1, remaining))
            if done:
                try:
                    return wrapped.result()
                except asyncio.CancelledError as exc:
                    raise HTTPException(status_code=499, detail="request cancelled") from exc
                except ValueError as exc:
                    raise HTTPException(status_code=413, detail=str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> JSONResponse:
        ready = bool(getattr(engine, "ready", False))
        payload = {
            "ready": ready,
            "queue_depth": worker.depth,
            "max_queue": settings.max_queue,
            "prewarm_ms": round(float(getattr(engine, "prewarm_ms", 0.0)), 1),
            "metrics": metrics.snapshot(),
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    @app.get("/metrics")
    def metrics_view() -> dict[str, Any]:
        return {
            "metrics": metrics.snapshot(),
            "queue_depth": worker.depth,
            "max_batch": settings.max_batch,
            "max_rows": settings.max_rows,
            "max_queue": settings.max_queue,
            "max_frames": settings.max_frames,
        }

    @app.post("/tts")
    async def tts(body: TTSRequest, request: Request) -> Response:
        validate([body.text], body.voice_profile, body.max_frames)
        chunks = engine.chunks_for(body.text, body.voice_profile)
        parts: list[Any] = []
        for chunk in chunks:
            try:
                job = worker.submit([chunk], body.max_frames, body.voice_profile)
            except QueueFull as exc:
                raise HTTPException(status_code=503, detail="queue is full") from exc
            audio = await wait_for(job, request)
            parts.append(audio[0])
        data = wav_bytes(concat_audio(parts), settings.sample_rate)
        return Response(content=data, media_type="audio/wav")

    @app.post("/tts/stream")
    async def tts_stream(body: TTSRequest, request: Request) -> StreamingResponse:
        validate([body.text], body.voice_profile, body.max_frames)
        chunks = engine.chunks_for(body.text, body.voice_profile)
        loop = asyncio.get_running_loop()
        chunks_out: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
        holder: dict[str, Any] = {}
        state: dict[str, Any] = {"index": 0, "job": None, "error": None}
        done = asyncio.Event()

        def put(data: bytes | None) -> None:
            try:
                chunks_out.put_nowait(data)
            except asyncio.QueueFull:
                job = holder.get("job")
                if job is not None:
                    job.cancelled = True
                    job.stop.set()
                metrics.add("slow_clients")

        def on_chunk(frame: Any, elapsed: float) -> None:
            data = pcm_bytes(frame)
            if data:
                loop.call_soon_threadsafe(put, data)

        def submit_next() -> asyncio.Future[Any]:
            index = state["index"]
            text = chunks[index]
            state["index"] = index + 1
            try:
                job = worker.submit(
                    [text], body.max_frames, body.voice_profile, on_chunk=on_chunk
                )
            except QueueFull as exc:
                state["error"] = HTTPException(status_code=503, detail="queue is full")
                done.set()
                raise
            state["job"] = job
            holder["job"] = job
            done.clear()

            def finished(future: asyncio.Future[Any]) -> None:
                try:
                    future.result()
                except BaseException as exc:
                    state["error"] = exc
                loop.call_soon_threadsafe(done.set)

            wrapped = asyncio.wrap_future(job.future)
            wrapped.add_done_callback(finished)
            return wrapped

        first_wait = submit_next()
        first_task = asyncio.create_task(chunks_out.get())
        done_first, _ = await asyncio.wait(
            {first_task, first_wait},
            timeout=settings.timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done_first:
            job = state["job"]
            if job is not None:
                job.cancelled = True
                job.stop.set()
            first_task.cancel()
            metrics.add("cancelled")
            raise HTTPException(status_code=504, detail="request timed out")
        if first_wait in done_first and state["error"] is not None:
            first_task.cancel()
            exc = state["error"]
            if isinstance(exc, HTTPException):
                raise exc
            if isinstance(exc, ValueError):
                raise HTTPException(status_code=413, detail=str(exc)) from exc
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        first = await first_task
        if first is None:
            raise HTTPException(status_code=500, detail="no audio")

        async def generate():
            job = state["job"]
            try:
                yield first
                while True:
                    if await request.is_disconnected():
                        if job is not None:
                            job.cancelled = True
                            job.stop.set()
                        metrics.add("cancelled")
                        break
                    if done.is_set():
                        if state["error"] is not None:
                            break
                        if state["index"] >= len(chunks):
                            while not chunks_out.empty():
                                rest = chunks_out.get_nowait()
                                if rest is not None:
                                    yield rest
                            break
                        submit_next()
                        job = state["job"]
                    try:
                        item = await asyncio.wait_for(chunks_out.get(), 0.05)
                    except asyncio.TimeoutError:
                        continue
                    if item is not None:
                        yield item
            finally:
                job = state["job"]
                if job is not None:
                    job.stop.set()

        return StreamingResponse(
            generate(),
            media_type="audio/L16",
            headers={
                "X-Sample-Rate": str(settings.sample_rate),
                "X-Channels": "1",
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/tts/batch")
    async def tts_batch(body: BatchRequest, request: Request) -> JSONResponse:
        validate(body.texts, body.voice_profile, body.max_frames)
        try:
            job = worker.submit(body.texts, body.max_frames, body.voice_profile)
        except QueueFull as exc:
            raise HTTPException(status_code=503, detail="queue is full") from exc
        audio = await wait_for(job, request)
        payload = [
            {
                "index": index,
                "samples": int(getattr(item, "numel", lambda: 0)()),
                "wav_base64": base64.b64encode(
                    wav_bytes(item, settings.sample_rate)
                ).decode("ascii"),
            }
            for index, item in enumerate(audio)
        ]
        return JSONResponse({"audio": payload})

    return app


app = create_app()
