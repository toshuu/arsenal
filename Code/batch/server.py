"""HTTP serving layer for one bounded T4 batch worker."""

from __future__ import annotations

import asyncio
import base64
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
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field


class QueueFull(Exception):
    pass


@dataclass
class Job:
    texts: list[str]
    max_frames: int | None
    future: Future = field(default_factory=Future)
    stop: threading.Event = field(default_factory=threading.Event)
    cancelled: bool = False
    created_at: float = field(default_factory=time.monotonic)


@dataclass
class Settings:
    max_batch: int = 8
    max_queue: int = 16
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

    def add(self, name: str, value: int = 1) -> None:
        with self.lock:
            setattr(self, name, getattr(self, name) + value)

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "completed": self.completed,
                "failed": self.failed,
                "cancelled": self.cancelled,
            }


class BatchWorker:
    def __init__(
        self,
        synthesize: Callable[..., list[Any]],
        max_batch: int,
        max_queue: int,
        metrics: Metrics,
    ) -> None:
        self.synthesize = synthesize
        self.max_batch = max_batch
        self.metrics = metrics
        self.jobs: queue.Queue[Job] = queue.Queue(maxsize=max_queue)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def depth(self) -> int:
        return self.jobs.qsize()

    def submit(self, texts: list[str], max_frames: int | None) -> Job:
        job = Job(texts=texts, max_frames=max_frames)
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
            deadline = time.monotonic() + 0.008
            while len(batch) < self.max_batch:
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
                batch.append(nxt)
            self._execute(batch)

    def _execute(self, batch: list[Job]) -> None:
        active = [job for job in batch if not job.cancelled]
        for job in batch:
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
        if not active:
            return
        texts = [text for job in active for text in job.texts]
        frames = [job.max_frames for job in active]
        max_frames = None if any(f is None for f in frames) else max(frames)
        stop = active[0].stop if len(active) == 1 else None
        try:
            audio = self.synthesize(texts, max_frames=max_frames, stop=stop)
        except Exception as exc:
            self.metrics.add("failed")
            for job in active:
                if not job.future.done():
                    job.future.set_exception(exc)
            return
        offset = 0
        for job in active:
            count = len(job.texts)
            part = audio[offset : offset + count]
            offset += count
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
            else:
                job.future.set_result(part)
                self.metrics.add("completed")


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
        self.ready = False

    def load(self) -> None:
        import logging
        import sys
        from pathlib import Path

        import torch

        code_root = Path(__file__).resolve().parents[1]
        model_dir = Path(os.getenv("ARSENAL_MODEL_DIR", code_root / "model"))
        sys.path.insert(0, str(code_root))
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
            torch.cuda.synchronize()
            self.ready = True
        finally:
            os.chdir(old)

    def synthesize(
        self, texts: list[str], max_frames: int | None = None, stop: Any = None
    ) -> list[Any]:
        if self.stream is None:
            raise RuntimeError("engine is not loaded")
        return self.stream.stream(texts, max_frames=max_frames, stop=stop)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    max_frames: int | None = Field(default=None, ge=1)


class BatchRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    max_frames: int | None = Field(default=None, ge=1)


def create_app(
    engine: Any | None = None,
    settings: Settings | None = None,
    start_engine: bool = True,
) -> FastAPI:
    settings = settings or Settings(
        max_batch=int(os.getenv("ARSENAL_MAX_BATCH", "8")),
        max_queue=int(os.getenv("ARSENAL_MAX_QUEUE", "16")),
        timeout_s=float(os.getenv("ARSENAL_TIMEOUT_S", "30")),
        max_texts=int(os.getenv("ARSENAL_MAX_TEXTS", "32")),
        max_chars=int(os.getenv("ARSENAL_MAX_CHARS", "4000")),
        sample_rate=int(os.getenv("ARSENAL_SAMPLE_RATE", "24000")),
    )
    metrics = Metrics()
    engine = engine or TTSEngine(settings)
    worker = BatchWorker(engine.synthesize, settings.max_batch, settings.max_queue, metrics)
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

    def validate(texts: list[str]) -> None:
        if len(texts) > settings.max_texts:
            raise HTTPException(status_code=413, detail="too many texts")
        for text in texts:
            if not text.strip():
                raise HTTPException(status_code=422, detail="empty text")
            if len(text) > settings.max_chars:
                raise HTTPException(status_code=413, detail="text is too long")

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
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> JSONResponse:
        ready = bool(getattr(engine, "ready", False))
        payload = {
            "ready": ready,
            "queue_depth": worker.depth,
            "max_queue": settings.max_queue,
            "metrics": metrics.snapshot(),
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    @app.get("/metrics")
    def metrics_view() -> dict[str, Any]:
        return {
            "metrics": metrics.snapshot(),
            "queue_depth": worker.depth,
            "max_batch": settings.max_batch,
            "max_queue": settings.max_queue,
        }

    @app.post("/tts")
    async def tts(body: TTSRequest, request: Request) -> Response:
        validate([body.text])
        try:
            job = worker.submit([body.text], body.max_frames)
        except QueueFull as exc:
            raise HTTPException(status_code=503, detail="queue is full") from exc
        audio = await wait_for(job, request)
        data = wav_bytes(audio[0], settings.sample_rate)
        return Response(content=data, media_type="audio/wav")

    @app.post("/tts/batch")
    async def tts_batch(body: BatchRequest, request: Request) -> JSONResponse:
        validate(body.texts)
        try:
            job = worker.submit(body.texts, body.max_frames)
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
