"""HTTP serving layer for one bounded T4 batch worker."""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import itertools
import os
import queue
import threading
import time
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

from batch.call_chunker import CALL_MODE, ChunkCache, estimate_first_max_frames, split_call_text
from batch.audio_join import join_chunks, smooth_chunk
from batch.pause_compress import StreamPauseCompressor, compress_long_pauses
from batch.job_classes import (
    PRIORITY,
    Config,
    JobClass,
    load_class_config,
    normal_limits,
    select_class,
)
from pydantic import BaseModel, Field


class QueueFull(Exception):
    pass


_CHUNK_POOL = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("ARSENAL_CHUNK_THREADS", "64")))
)


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
    priority: int = 0
    seq: int = 0
    job_class: JobClass = JobClass.NORMAL
    mode: str = "normal"
    started_at: float | None = None
    first_chunk_at: float | None = None
    pcm: bytes | None = None
    t: dict[str, int] = field(default_factory=dict)
    cap_hit: bool = False
    chunk_texts: list[str] = field(default_factory=list)


@dataclass
class Settings:
    max_batch: int = 224
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
        self.request_first_ms: list[float] = []
        self.total_ms: list[float] = []
        self.chunk_ms: list[float] = []
        self.batch_size: list[float] = []
        self.batch_spread_ms: list[float] = []
        self.batch_wait_ms: list[float] = []
        self.batch_wall_ms: list[float] = []
        self.arrival_ms: list[float] = []
        self.bursts: dict[str, list[float]] = {}
        self.burst_t0: dict[str, float] = {}
        self.handler_offset_ms: list[float] = []
        self.validate_offset_ms: list[float] = []
        self.chunks_offset_ms: list[float] = []
        self.submit_offset_ms: list[float] = []
        self.validate_ms: list[float] = []
        self.vram_alloc_before_mb: list[float] = []
        self.vram_alloc_after_mb: list[float] = []
        self.vram_peak_mb: list[float] = []
        self.vram_reserved_mb: list[float] = []
        self.timeline: dict[str, list[float]] = {} if os.getenv("ARSENAL_TIMELINE") == "1" else None
        self.call_first_ms: list[float] = []
        self.call_first_wait_ms: list[float] = []
        self.call_wait_behind_normal_ms: list[float] = []
        self.class_first_ms: dict[str, list[float]] = {
            cls.value: [] for cls in JobClass
        }
        self.last_normal_end = 0.0
        self.active_calls = 0
        self.underruns = 0
        self.batch_classes: list[str] = []
        self.ws_text_to_submit_ms: list[float] = []
        self.ws_text_to_first_byte_ms: list[float] = []
        self.ws_send_to_recv_ms: list[float] = []
        self.ws_job_wait_ms: list[float] = []
        self.ws_pcm_ms: list[float] = []
        self.ws_send_ms: list[float] = []
        self.ws_after_emit_ms: list[float] = []

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

    def reset(self) -> None:
        with self.lock:
            self.accepted = 0
            self.rejected = 0
            self.completed = 0
            self.failed = 0
            self.cancelled = 0
            self.slow_clients = 0
            self.last_errors = []
            self.queue_ms = []
            self.first_ms = []
            self.request_first_ms = []
            self.total_ms = []
            self.chunk_ms = []
            self.batch_size = []
            self.batch_spread_ms = []
            self.batch_wait_ms = []
            self.arrival_ms = []
            self.bursts = {}
            self.burst_t0 = {}
            self.handler_offset_ms = []
            self.validate_offset_ms = []
            self.chunks_offset_ms = []
            self.submit_offset_ms = []
            self.validate_ms = []
            self.vram_alloc_before_mb = []
            self.vram_alloc_after_mb = []
            self.vram_peak_mb = []
            self.vram_reserved_mb = []
            if self.timeline is not None:
                self.timeline = {}

    def record_arrival(self, sent_at_ns: int, burst_id: str | None) -> None:
        now_ns = time.time_ns()
        latency = (now_ns - sent_at_ns) / 1e6
        with self.lock:
            self.arrival_ms.append(latency)
            del self.arrival_ms[:-2000]
            if burst_id:
                self.bursts.setdefault(burst_id, []).append(time.monotonic() * 1000.0)
                if len(self.bursts) > 500:
                    for key in list(self.bursts)[: len(self.bursts) - 500]:
                        del self.bursts[key]
                        self.burst_t0.pop(key, None)

    def record_stage_offsets(
        self,
        burst_id: str | None,
        handler_ns: int,
        validate_ns: int,
        chunks_ns: int,
        submit_ns: int,
    ) -> None:
        if not burst_id:
            return
        h = handler_ns / 1e6
        with self.lock:
            t0 = self.burst_t0.get(burst_id)
            if t0 is None or h < t0:
                self.burst_t0[burst_id] = h
                t0 = h
            self.handler_offset_ms.append(h - t0)
            self.validate_offset_ms.append(validate_ns / 1e6 - t0)
            self.chunks_offset_ms.append(chunks_ns / 1e6 - t0)
            self.submit_offset_ms.append(submit_ns / 1e6 - t0)
            self.validate_ms.append((validate_ns - handler_ns) / 1e6)
            for lst in (
                self.handler_offset_ms,
                self.validate_offset_ms,
                self.chunks_offset_ms,
                self.submit_offset_ms,
                self.validate_ms,
            ):
                del lst[:-2000]

    def record_vram(self, before: float, after: float, peak: float, reserved: float) -> None:
        with self.lock:
            self.vram_alloc_before_mb.append(before)
            self.vram_alloc_after_mb.append(after)
            self.vram_peak_mb.append(peak)
            self.vram_reserved_mb.append(reserved)
            for lst in (self.vram_alloc_before_mb, self.vram_alloc_after_mb, self.vram_peak_mb, self.vram_reserved_mb):
                del lst[:-1000]

    def record_batch(self, size: int, spread_ms: float, wait_ms: float) -> None:
        with self.lock:
            self.batch_size.append(float(size))
            self.batch_spread_ms.append(spread_ms)
            self.batch_wait_ms.append(wait_ms)
            del self.batch_size[:-1000]
            del self.batch_spread_ms[:-1000]
            del self.batch_wait_ms[:-1000]

    def record_batch_wall(self, wall_ms: float) -> None:
        with self.lock:
            self.batch_wall_ms.append(wall_ms)
            del self.batch_wall_ms[:-1000]

    def record_chunk(self, value_ms: float) -> None:
        with self.lock:
            self.chunk_ms.append(value_ms)
            del self.chunk_ms[:-1000]

    def record_request_first(self, value_ms: float) -> None:
        with self.lock:
            self.request_first_ms.append(value_ms)
            del self.request_first_ms[:-1000]

    def record_timeline(self, data: dict[str, int], first_only: bool = False) -> None:
        if self.timeline is None or not data:
            return
        # continuation chunks have large handler-to-submit gap and no first_byte_sent from request
        if first_only and not data.get("ws") and "submit" in data and "handler" in data:
            if (data["submit"] - data["handler"]) / 1e6 > 500:
                return
        order = [
            "handler", "chunks_done", "submit", "batch_start", "stream_start",
            "prep_done", "cond_done", "flow0_done", "mimi0_done", "first_emit",
            "loop_delivered", "first_byte_sent",
        ]
        vals: dict[str, float] = {}
        prev = None
        for name in order:
            if name in data:
                if prev is not None and prev in data:
                    vals[f"{prev}_to_{name}_ms"] = (data[name] - data[prev]) / 1e6
                prev = name
        if "handler" in data and "first_byte_sent" in data:
            vals["handler_to_first_byte_ms"] = (data["first_byte_sent"] - data["handler"]) / 1e6
        with self.lock:
            for k, v in vals.items():
                arr = self.timeline.setdefault(k, [])
                arr.append(v)
                del arr[:-2000]

    def set_active_calls(self, value: int) -> None:
        with self.lock:
            self.active_calls = value

    def record_call_first(self, value_ms: float) -> None:
        with self.lock:
            self.call_first_ms.append(value_ms)

    def record_call_wait(self, value_ms: float) -> None:
        with self.lock:
            if value_ms >= 0:
                self.call_first_wait_ms.append(value_ms)

    def record_first_class(self, name: str, value_ms: float) -> None:
        with self.lock:
            self.class_first_ms.setdefault(name, []).append(value_ms)

    def note_normal_end(self, when: float) -> None:
        with self.lock:
            self.last_normal_end = max(self.last_normal_end, when)

    def record_call_wait_behind_normal(self, created_at: float, value_ms: float) -> None:
        with self.lock:
            if created_at < self.last_normal_end and value_ms >= 0:
                self.call_wait_behind_normal_ms.append(value_ms)

    def record_batch_class(self, name: str) -> None:
        with self.lock:
            self.batch_classes.append(name)
            del self.batch_classes[:-200]

    def record_ws_timing(self, to_submit: float | None, to_first: float | None, send_to_recv: float | None) -> None:
        with self.lock:
            if to_submit is not None:
                self.ws_text_to_submit_ms.append(to_submit)
                del self.ws_text_to_submit_ms[:-2000]
            if to_first is not None:
                self.ws_text_to_first_byte_ms.append(to_first)
                del self.ws_text_to_first_byte_ms[:-2000]
            if send_to_recv is not None:
                self.ws_send_to_recv_ms.append(send_to_recv)
                del self.ws_send_to_recv_ms[:-2000]

    def record_ws_phase(self, job_wait: float, pcm: float, send: float, after_emit: float | None) -> None:
        with self.lock:
            self.ws_job_wait_ms.append(job_wait)
            self.ws_pcm_ms.append(pcm)
            self.ws_send_ms.append(send)
            del self.ws_job_wait_ms[:-2000]
            del self.ws_pcm_ms[:-2000]
            del self.ws_send_ms[:-2000]
            if after_emit is not None:
                self.ws_after_emit_ms.append(after_emit)
                del self.ws_after_emit_ms[:-2000]

    def add_underrun(self) -> None:
        with self.lock:
            self.underruns += 1

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            out = {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "completed": self.completed,
                "failed": self.failed,
                "cancelled": self.cancelled,
                "slow_clients": self.slow_clients,
                "last_errors": self.last_errors[-5:],
                "queue_ms": self._stats(self.queue_ms),
                "first_chunk_ms": self._stats(self.first_ms),
                "request_first_chunk_ms": self._stats(self.request_first_ms),
                "total_ms": self._stats(self.total_ms),
                "chunk_ms": self._stats(self.chunk_ms),
                "batch_size": self._stats(self.batch_size),
                "batch_spread_ms": self._stats(self.batch_spread_ms),
                "batch_wait_ms": self._stats(self.batch_wait_ms),
                "batch_wall_ms": self._stats(self.batch_wall_ms),
                "arrival_ms": self._stats(self.arrival_ms),
                "burst_spread_ms": self._stats(
                    [max(v) - min(v) for v in self.bursts.values() if len(v) > 1]
                ),
                "handler_offset_ms": self._stats(self.handler_offset_ms),
                "validate_offset_ms": self._stats(self.validate_offset_ms),
                "chunks_offset_ms": self._stats(self.chunks_offset_ms),
                "submit_offset_ms": self._stats(self.submit_offset_ms),
                "validate_ms": self._stats(self.validate_ms),
                "vram_alloc_before_mb": self._stats(self.vram_alloc_before_mb),
                "vram_alloc_after_mb": self._stats(self.vram_alloc_after_mb),
                "vram_peak_mb": self._stats(self.vram_peak_mb),
                "vram_reserved_mb": self._stats(self.vram_reserved_mb),
                "call_first_ms": self._stats(self.call_first_ms),
                "call_first_wait_ms": self._stats(self.call_first_wait_ms),
                "call_first_wait_behind_normal_ms": self._stats(
                    self.call_wait_behind_normal_ms
                ),
                "first_chunk_ms_by_class": {
                    name: self._stats(values)
                    for name, values in self.class_first_ms.items()
                },
                "ws_text_to_submit_ms": self._stats(self.ws_text_to_submit_ms),
                "ws_text_to_first_byte_ms": self._stats(self.ws_text_to_first_byte_ms),
                "ws_send_to_recv_ms": self._stats(self.ws_send_to_recv_ms),
                "ws_job_wait_ms": self._stats(self.ws_job_wait_ms),
                "ws_pcm_ms": self._stats(self.ws_pcm_ms),
                "ws_send_ms": self._stats(self.ws_send_ms),
                "ws_after_emit_ms": self._stats(self.ws_after_emit_ms),
                "active_call_sessions": self.active_calls,
                "underruns": self.underruns,
                "batch_classes": list(self.batch_classes[-20:]),
            }
            if self.timeline is not None:
                out["timeline_p95"] = {k: self._stats(v)["p95"] for k, v in self.timeline.items()}
                out["timeline_p50"] = {k: self._stats(v)["p50"] for k, v in self.timeline.items()}
            return out


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
        self.cfg: Config = load_class_config()
        self.queues: dict[JobClass, queue.PriorityQueue] = {
            cls: queue.PriorityQueue(maxsize=max_queue) for cls in JobClass
        }
        self.cond = threading.Condition()
        self.seq = itertools.count()
        self.active_call_sessions = 0
        self.last_enqueue = {cls: 0.0 for cls in JobClass}
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def depth(self) -> int:
        return sum(q.qsize() for q in self.queues.values())

    def enter_call(self) -> None:
        with self.cond:
            self.active_call_sessions += 1
            self.metrics.set_active_calls(self.active_call_sessions)
            self.cond.notify_all()

    def exit_call(self) -> None:
        with self.cond:
            self.active_call_sessions = max(0, self.active_call_sessions - 1)
            self.metrics.set_active_calls(self.active_call_sessions)
            self.cond.notify_all()

    def reload_config(self) -> None:
        self.cfg = load_class_config()

    def submit(
        self,
        texts: list[str],
        max_frames: int | None,
        profile_id: str | None = None,
        on_chunk: Callable[..., None] | None = None,
        priority: int | None = None,
        job_class: JobClass | str = JobClass.NORMAL,
        mode: str = "normal",
    ) -> Job:
        cls = job_class if isinstance(job_class, JobClass) else JobClass(job_class)
        if cls is not JobClass.NORMAL and max_frames is None:
            max_frames = self.cfg.classes[cls].max_frames
        job = Job(
            texts=texts,
            max_frames=max_frames,
            profile_id=profile_id,
            on_chunk=on_chunk,
            priority=PRIORITY[cls] if priority is None else priority,
            job_class=cls,
            mode=mode,
            seq=next(self.seq),
        )
        if len(texts) > self.max_rows:
            self.metrics.add("rejected")
            raise QueueFull("too many rows")
        try:
            self.queues[cls].put_nowait((job.priority, job.seq, job))
        except queue.Full as exc:
            self.metrics.add("rejected")
            raise QueueFull("queue is full") from exc
        with self.cond:
            self.last_enqueue[cls] = time.monotonic()
            self.cond.notify_all()
        self.metrics.add("accepted")
        return job

    def _run(self) -> None:
        while True:
            with self.cond:
                cls = select_class(self.queues, self.active_call_sessions)
                if cls is None:
                    self.cond.wait(timeout=0.25)
                    continue
            batch = self._collect(cls)
            if not batch:
                continue
            if cls is JobClass.NORMAL and self.active_call_sessions > 0:
                q_wait = float(os.getenv("ARSENAL_CALL_FIRST_QUIET_MS", "0"))
                last_cf = self.last_enqueue.get(JobClass.CALL_FIRST, 0.0)
                call_pending = (
                    not self.queues[JobClass.CALL_FIRST].empty()
                    or not self.queues[JobClass.CALL_CONT].empty()
                    or (q_wait > 0 and (time.monotonic() - last_cf) * 1000.0 < q_wait)
                )
                if call_pending:
                    for job in batch:
                        self.queues[cls].put_nowait((job.priority, job.seq, job))
                    with self.cond:
                        self.cond.wait(timeout=0.005)
                    continue
            batches = [batch]
            if cls is JobClass.CALL_FIRST:
                # absorb late arrivals once before first GPU step
                q = self.queues[cls]
                for _ in range(8):
                    while True:
                        try:
                            _, _, job = q.get_nowait()
                        except queue.Empty:
                            break
                        if job.cancelled:
                            job.future.set_exception(asyncio.CancelledError())
                            self.metrics.add("cancelled")
                            continue
                        batch.append(job)
                    if q.empty():
                        break
                batches = [batch]
            for b in batches:
                created = [job.created_at for job in b]
                self.metrics.record_batch(
                    len(b),
                    (max(created) - min(created)) * 1000.0 if len(created) > 1 else 0.0,
                    (time.monotonic() - min(created)) * 1000.0,
                )
                self.metrics.record_batch_class(cls.value)
                t_exec = time.monotonic()
                self._execute(b)
                self.metrics.record_batch_wall((time.monotonic() - t_exec) * 1000.0)
            if cls is JobClass.NORMAL:
                self.metrics.note_normal_end(time.monotonic())

    def _collect(self, cls: JobClass) -> list[Job]:
        cfg = self.cfg.classes[cls]
        limit = min(cfg.max_batch, self.max_batch, self.max_rows)
        if cls is JobClass.CALL_FIRST:
            limit = min(
                int(os.getenv("ARSENAL_CALL_FIRST_MAX_BATCH", str(limit))),
                self.max_batch,
                self.max_rows,
            )
            q_ms = float(os.getenv("ARSENAL_CALL_FIRST_QUIET_MS", "0"))
            h_ms = float(os.getenv("ARSENAL_CALL_FIRST_HARD_CAP_MS", "0"))
            if os.getenv("ARSENAL_CALL_POISSON") == "1":
                h_ms = min(h_ms, 10.0) if h_ms > 0 else 10.0
            if q_ms > 0 or h_ms > 0:
                return self._collect_call_first_quiet(cls, limit, q_ms, h_ms)
            sub_limit = min(
                int(os.getenv("ARSENAL_CALL_FIRST_SUB_BATCH", str(limit))), limit
            )
            limit = sub_limit
        if cls is JobClass.NORMAL:
            limit, _ = normal_limits(self.cfg, self.active_call_sessions)
            limit = min(limit, self.max_batch, self.max_rows)
        target = min(int(os.getenv("ARSENAL_BATCH_TARGET", str(limit))), limit, self.max_rows)
        deadline = time.monotonic() + cfg.window_ms / 1000.0
        batch: list[Job] = []
        rows = 0
        while len(batch) < limit and rows < self.max_rows:
            try:
                _, _, job = self.queues[cls].get_nowait()
            except queue.Empty:
                if len(batch) >= target:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                with self.cond:
                    self.cond.wait(timeout=remaining)
                try:
                    _, _, job = self.queues[cls].get_nowait()
                except queue.Empty:
                    break
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
                continue
            if rows + len(job.texts) > self.max_rows:
                self.queues[cls].put_nowait((job.priority, job.seq, job))
                break
            batch.append(job)
            rows += len(job.texts)
        return batch

    def _frame_bucket(self, job: Job) -> int:
        mf = int(job.max_frames or 48)
        for b in (24, 48, 96, 192):
            if mf <= b:
                return b
        return 192

    def _collect_call_first_quiet(
        self, cls: JobClass, limit: int, q_ms: float, h_ms: float
    ) -> list[Job]:
        q = self.queues[cls]
        batch: list[Job] = []
        start: float | None = None
        grace_ms = float(os.getenv("ARSENAL_CALL_FIRST_GRACE_MS", "0"))
        use_buckets = os.getenv("ARSENAL_CALL_FIRST_BUCKETS", "1") == "1"
        while True:
            drained = False
            while True:
                try:
                    _, _, job = q.get_nowait()
                except queue.Empty:
                    break
                drained = True
                if job.cancelled:
                    job.future.set_exception(asyncio.CancelledError())
                    self.metrics.add("cancelled")
                    continue
                batch.append(job)
                if start is None:
                    start = time.monotonic()
            if not batch:
                with self.cond:
                    self.cond.wait(timeout=0.25)
                continue
            if self.active_call_sessions > 0 and len(batch) >= self.active_call_sessions:
                break
            now = time.monotonic()
            last = self.last_enqueue.get(cls, start)
            quiet = q_ms <= 0 or (now - last) * 1000.0 >= q_ms
            hard = h_ms > 0 and (now - start) * 1000.0 >= h_ms
            if hard or (quiet and not drained):
                if not hard and grace_ms > 0:
                    with self.cond:
                        self.cond.wait(timeout=grace_ms / 1000.0)
                for _ in range(8):
                    while True:
                        try:
                            _, _, job = q.get_nowait()
                        except queue.Empty:
                            break
                        if job.cancelled:
                            job.future.set_exception(asyncio.CancelledError())
                            self.metrics.add("cancelled")
                            continue
                        batch.append(job)
                    if q.empty():
                        break
                break
            if drained:
                continue
            waits = []
            if q_ms > 0:
                waits.append(max(0.0, q_ms / 1000.0 - (now - last)))
            if h_ms > 0:
                waits.append(max(0.0, h_ms / 1000.0 - (now - start)))
            wait = min(waits) if waits else 0.001
            with self.cond:
                self.cond.wait(timeout=min(max(wait, 0.0), 0.01))
        if not use_buckets or len(batch) <= 1:
            return batch
        # form batch within one bucket; requeue rest
        groups: dict[int, list[Job]] = {}
        for j in batch:
            groups.setdefault(self._frame_bucket(j), []).append(j)
        # pick bucket with most rows, tie by smallest bucket (lower latency)
        pick = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0][0]
        chosen = groups[pick][:limit]
        rest = [j for b, js in groups.items() for j in (js if b != pick else js[limit:])]
        for j in rest:
            self.queues[cls].put_nowait((j.priority, j.seq, j))
        with self.cond:
            self.cond.notify_all()
        return chosen

    def _execute(self, batch: list[Job]) -> None:
        active = [job for job in batch if not job.cancelled]
        for job in batch:
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
        if not active:
            return
        keys = {job.profile_id for job in active}
        profile_id = next(iter(keys)) if len(keys) == 1 else None
        self._execute_group(active, profile_id)
        if os.getenv("ARSENAL_EMPTY_CACHE") == "1":
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def _execute_group(self, jobs: list[Job], profile_id: str | None) -> None:
        texts = [text for job in jobs for text in job.texts]
        owners = [job for job in jobs for _ in job.texts]
        frames = [job.max_frames for job in jobs]
        max_frames = None if any(f is None for f in frames) else max(frames)
        stop = jobs[0].stop if len(jobs) == 1 else None
        for job in jobs:
            job.started_at = time.monotonic()
            job.t["batch_start"] = time.perf_counter_ns()

        def relay(row: int, frame: Any, elapsed: float) -> None:
            job = owners[row]
            now = time.monotonic()
            if job.first_chunk_at is None:
                job.first_chunk_at = now
                job.t.setdefault("first_emit", time.perf_counter_ns())
            if job.on_chunk is not None:
                job.on_chunk(frame, elapsed)

        def on_stage(row: int, name: str, at: float) -> None:
            ns = int(at * 1e9)
            if row < 0:
                for j in jobs:
                    j.t.setdefault(name, ns)
            else:
                owners[row].t[name] = ns

        try:
            profile_ids = [
                job.profile_id for job in jobs for _ in job.texts
            ]
            vram = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats()
                    a0 = torch.cuda.memory_allocated() / (1024 * 1024)
                    r0 = torch.cuda.memory_reserved() / (1024 * 1024)
                    vram = (a0, r0)
            except Exception:
                vram = None
            for j in jobs:
                j.t["synth_start"] = time.perf_counter_ns()
            audio = self.engine.synthesize(
                texts,
                max_frames=max_frames,
                stop=stop,
                profile_id=profile_id,
                profile_ids=profile_ids,
                on_chunk=relay,
                on_stage=on_stage,
            )
            for j in jobs:
                j.t["synth_end"] = time.perf_counter_ns()
            _trunc_stream = self.engine._stream_for(profile_id) if profile_id is not None or len({j.profile_id for j in jobs})==1 else getattr(self.engine, "mixed_stream", None)
            trunc = list(getattr(_trunc_stream, "last_truncated_rows", []) or []) if _trunc_stream is not None else []
            if trunc:
                for r in trunc:
                    if 0 <= r < len(owners):
                        owners[r].cap_hit = True
            if vram is not None:
                try:
                    import torch
                    torch.cuda.synchronize()
                    a1 = torch.cuda.memory_allocated() / (1024 * 1024)
                    r1 = torch.cuda.memory_reserved() / (1024 * 1024)
                    p1 = torch.cuda.max_memory_allocated() / (1024 * 1024)
                    self.metrics.record_vram(vram[0], a1, p1, r1)
                except Exception:
                    pass
        except Exception as exc:
            if vram is not None:
                try:
                    import torch
                    torch.cuda.synchronize()
                    a1 = torch.cuda.memory_allocated() / (1024 * 1024)
                    p1 = torch.cuda.max_memory_allocated() / (1024 * 1024)
                    r1 = torch.cuda.memory_reserved() / (1024 * 1024)
                    self.metrics.record_vram(vram[0], a1, p1, r1)
                except Exception:
                    pass
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
            if first is not None:
                self.metrics.record_first_class(job.job_class.value, first)
            if job.job_class is JobClass.CALL_FIRST:
                if first is not None:
                    self.metrics.record_call_first(first)
                wait = (started - job.created_at) * 1000.0
                self.metrics.record_call_wait(wait)
                self.metrics.record_call_wait_behind_normal(job.created_at, wait)
            self.metrics.record_timeline(job.t, first_only=True)
            if job.cancelled:
                job.future.set_exception(asyncio.CancelledError())
                self.metrics.add("cancelled")
            else:
                if (
                    job.mode == CALL_MODE
                    and job.job_class is JobClass.CALL_CONT
                    and len(part) == 1
                ):
                    job.pcm = pcm_bytes(part[0])
                job.future.set_result(part)
                self.metrics.add("completed")


def concat_audio(parts: list[Any]) -> Any:
    if len(parts) == 1:
        return parts[0]
    arrays = []
    for part in parts:
        if hasattr(part, "detach"):
            part = part.detach().float().cpu().numpy()
        arrays.append(np.asarray(part, dtype="float32"))
    return np.concatenate(arrays)



def _norm_text(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", " ".join(re.findall(r"[a-z0-9']+", (s or "").lower()))).strip()


def _assert_text_integrity(input_text: str, chunk_texts: list[str]) -> None:
    a = _norm_text(input_text)
    b = _norm_text(" ".join(chunk_texts))
    if a != b:
        raise HTTPException(status_code=500, detail=f"text integrity failed: in={a!r} out={b!r}")

def pcm_bytes(samples: Any) -> bytes:
    if hasattr(samples, "detach"):
        samples = samples.detach().float().cpu().numpy()
    data = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    return (data * 32767.0).astype("<i2").tobytes()


def wav_bytes(samples: Any, sample_rate: int) -> bytes:
    if hasattr(samples, "detach"):
        samples = samples.detach().float().cpu().numpy()
    data = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buf.getvalue()


def _stats_list(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    data = sorted(values)
    return {
        "count": len(data),
        "p50": round(data[len(data) // 2], 2),
        "p95": round(data[min(len(data) - 1, int(len(data) * 0.95))], 2),
        "max": round(data[-1], 2),
    }


def _vram_mb() -> dict[str, float]:
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "alloc": round(torch.cuda.memory_allocated() / 1e6, 1),
                "reserved": round(torch.cuda.memory_reserved() / 1e6, 1),
            }
    except Exception:
        pass
    return {"alloc": 0.0, "reserved": 0.0}


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
            nt = os.getenv("ARSENAL_TORCH_THREADS")
            if nt:
                torch.set_num_threads(max(1, int(nt)))
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
            try:
                torch.cuda.synchronize()
                print(f"VRAM load alloc={torch.cuda.memory_allocated()/1024**2:.0f}MB reserved={torch.cuda.memory_reserved()/1024**2:.0f}MB", flush=True)
            except Exception:
                pass
            self.prewarm_ms = maybe_prewarm(self.stream, ["Ready."] * max(1, n))
            torch.cuda.synchronize()
            try:
                print(f"VRAM prewarm alloc={torch.cuda.memory_allocated()/1024**2:.0f}MB reserved={torch.cuda.memory_reserved()/1024**2:.0f}MB peak={torch.cuda.max_memory_allocated()/1024**2:.0f}MB", flush=True)
            except Exception:
                pass
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
            stream._chunk_cache = dict(getattr(source, "_chunk_cache", {}))
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
        on_stage: Callable[..., None] | None = None,
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
                texts, max_frames=max_frames, stop=stop, on_chunk=on_chunk, on_stage=on_stage
            )
        stream = self._stream_for(profile_id)
        conditioned = profile_id is not None or self.default_is_profile
        if conditioned and len(texts) > 1:
            keys = {self.batch_key(text, profile_id) for text in texts}
            if len(keys) > 1:
                stream = self._normal_stream(profile_id)
        return stream.stream(
            texts, max_frames=max_frames, stop=stop, on_chunk=on_chunk, on_stage=on_stage
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
        max_batch=int(os.getenv("ARSENAL_MAX_BATCH", "224")),
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
    app.state.chunk_cache = ChunkCache()

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

    def _note_arrival(request: Request) -> None:
        sent = request.headers.get("x-sent-at")
        if not sent:
            return
        try:
            metrics.record_arrival(int(sent), request.headers.get("x-burst-id"))
        except Exception:
            pass

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
            "batch_window_ms": int(os.getenv("ARSENAL_BATCH_WINDOW_MS", "150")),
        }

    @app.get("/debug/reset")
    def debug_reset() -> dict[str, Any]:
        if os.getenv("ARSENAL_DEBUG") != "1":
            raise HTTPException(status_code=404, detail="not found")
        metrics.reset()
        return {"ok": True}

    @app.post("/tts")
    async def tts(body: TTSRequest, request: Request) -> Response:
        t0 = time.perf_counter_ns()
        _note_arrival(request)
        validate([body.text], body.voice_profile, body.max_frames)
        t_validate = time.perf_counter_ns()
        call_mode = request.query_params.get("mode") == "call"
        if call_mode:
            stream = engine._stream_for(body.voice_profile)
            requested = int(request.query_params.get("first_max_frames", "0") or 0)
            est = estimate_first_max_frames(stream, body.text)
            first_frames = requested if requested > 0 else int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES", str(est)))
            first_frames = max(16, min(first_frames, body.max_frames))
            cache: ChunkCache = app.state.chunk_cache
            chunks = await asyncio.get_running_loop().run_in_executor(
                _CHUNK_POOL, cache.get_or_split, (body.text, first_frames),
                lambda: split_call_text(stream, body.text, first_frames),
            )
        else:
            chunks = await asyncio.get_running_loop().run_in_executor(
                _CHUNK_POOL, engine.chunks_for, body.text, body.voice_profile
            )
        t1 = time.perf_counter_ns()
        metrics.record_chunk((t1 - t_validate) / 1e6)
        parts: list[Any] = []
        chunk_logs=[]
        call_mode = request.query_params.get("mode") == "call"
        for i, chunk in enumerate(chunks):
            mf = body.max_frames
            if call_mode:
                est = estimate_first_max_frames(engine._stream_for(body.voice_profile), chunk)
                mf = max(24, min(int(est), body.max_frames))
            try:
                job = worker.submit([chunk], mf, body.voice_profile, priority=0, mode=CALL_MODE if call_mode else "normal",
                                    job_class=JobClass.CALL_FIRST if call_mode and i==0 else (JobClass.CALL_CONT if call_mode else JobClass.NORMAL))
            except QueueFull as exc:
                raise HTTPException(status_code=503, detail="queue is full") from exc
            t_sub = time.perf_counter_ns()
            if i == 0:
                metrics.record_stage_offsets(request.headers.get("x-burst-id"), t0, t_validate, t1, t_sub)
            job.t.setdefault("handler", t0); job.t.setdefault("chunks_done", t1); job.t.setdefault("submit", t_sub)
            audio = await wait_for(job, request)
            arr = audio[0].detach().float().cpu().numpy() if hasattr(audio[0], 'detach') else np.asarray(audio[0], dtype=np.float32)
            parts.append(arr)
            chunk_logs.append({"index":i,"text":chunk,"frames_cap":mf,"cap_hit":bool(getattr(job,'cap_hit',False)),"audio_sec":len(arr)/settings.sample_rate})
            if getattr(job,'cap_hit',False):
                log.warning("CAP_HIT /tts chunk=%s frames=%s text=%r", i, mf, chunk)
        if call_mode:
            _assert_text_integrity(body.text, [c["text"] for c in chunk_logs])
            joined = join_chunks(parts, sr=settings.sample_rate, pause_ms=100)
            joined = compress_long_pauses(joined, sr=settings.sample_rate)
            data = wav_bytes(torch.from_numpy(joined), settings.sample_rate)
        else:
            data = wav_bytes(concat_audio([torch.from_numpy(p) if not hasattr(p,'dtype') or str(p.dtype).startswith('float') else torch.from_numpy(p.astype('float32')) for p in parts]), settings.sample_rate)
        return Response(content=data, media_type="audio/wav")

    @app.post("/tts/stream")
    async def tts_stream(body: TTSRequest, request: Request) -> StreamingResponse:
        request_start = time.monotonic()
        t_handler = time.perf_counter_ns()
        _note_arrival(request)
        validate([body.text], body.voice_profile, body.max_frames)
        t_validate = time.perf_counter_ns()
        call_mode = request.query_params.get("mode") == "call"
        if call_mode:
            stream = engine._stream_for(body.voice_profile)
            requested = int(request.query_params.get("first_max_frames", "0") or 0)
            est = estimate_first_max_frames(stream, body.text)
            first_frames = requested if requested > 0 else int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES", str(est)))
            first_frames = max(16, min(first_frames, body.max_frames))
            cont_frames = min(
                int(os.getenv("ARSENAL_CALL_CONT_MAX_FRAMES", "192")), body.max_frames
            )
            cache: ChunkCache = app.state.chunk_cache
            chunks = await asyncio.get_running_loop().run_in_executor(
                _CHUNK_POOL,
                cache.get_or_split,
                (body.text, first_frames),
                lambda: split_call_text(stream, body.text, first_frames),
            )
        else:
            first_frames = body.max_frames
            cont_frames = body.max_frames
            chunks = await asyncio.get_running_loop().run_in_executor(
                _CHUNK_POOL, engine.chunks_for, body.text, body.voice_profile
            )
        t_chunks = time.perf_counter_ns()
        metrics.record_chunk((t_chunks - t_validate) / 1e6)
        loop = asyncio.get_running_loop()
        chunks_out: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
        holder: dict[str, Any] = {}
        state: dict[str, Any] = {"index": 0, "job": None, "error": None}
        done = asyncio.Event()

        def put(data: bytes | None) -> None:
            job = holder.get("job")
            if job is not None:
                job.t.setdefault("loop_delivered", time.perf_counter_ns())
            try:
                chunks_out.put_nowait(data)
            except asyncio.QueueFull:
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
            priority = 0 if index == 0 else 1
            state["index"] = index + 1
            frames = first_frames if index == 0 else cont_frames
            if call_mode:
                cls = JobClass.CALL_FIRST if index == 0 else JobClass.CALL_CONT
                kwargs: dict[str, Any] = {"job_class": cls, "mode": CALL_MODE}
            else:
                kwargs = {"priority": priority}
            try:
                job = worker.submit(
                    [text],
                    frames,
                    body.voice_profile,
                    on_chunk=on_chunk,
                    **kwargs,
                )
            except QueueFull as exc:
                state["error"] = HTTPException(status_code=503, detail="queue is full")
                done.set()
                raise
            t_sub = time.perf_counter_ns()
            job.t.setdefault("handler", t_handler)
            job.t.setdefault("chunks_done", t_chunks)
            job.t.setdefault("submit", t_sub)
            if index == 0:
                metrics.record_stage_offsets(
                    request.headers.get("x-burst-id"), t_handler, t_validate, t_chunks, t_sub
                )
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
        fj = state.get("job")
        if fj is not None:
            fj.t.setdefault("first_byte_sent", time.perf_counter_ns())
        metrics.record_request_first((time.monotonic() - request_start) * 1000.0)

        async def generate():
            try:
                if not call_mode:
                    job = state["job"]
                    yield first
                    while True:
                        if await request.is_disconnected():
                            job = state.get("job")
                            if job is not None:
                                job.cancelled = True; job.stop.set()
                            metrics.add("cancelled"); break
                        if done.is_set():
                            if state["error"] is not None: break
                            if state["index"] >= len(chunks):
                                while not chunks_out.empty():
                                    rest = chunks_out.get_nowait()
                                    if rest is not None: yield rest
                                break
                            submit_next(); job = state["job"]
                        try:
                            item = await asyncio.wait_for(chunks_out.get(), 0.05)
                        except asyncio.TimeoutError:
                            continue
                        if item is not None: yield item
                    return
                # call mode: collect per-chunk full audio from already-submitted pipeline? easier: rebuild as smoothed prefetch
                sr = settings.sample_rate
                holdback = int(sr * 0.04)
                prev_tail = np.zeros(0, dtype=np.float32)
                prev_rms = None
                chunk_meta = []
                pause_comp = StreamPauseCompressor(sr=sr, holdback_ms=50)
                def _yield_pcm(arr, final=False):
                    out = pause_comp.push(arr, final=final)
                    if out.size == 0:
                        return b""
                    return (np.clip(out,-1,1)*32767).astype('<i2').tobytes()

                async def run_one(idx, ch):
                    mf = first_frames if idx == 0 else cont_frames
                    frame_q: asyncio.Queue = asyncio.Queue()
                    first_ev = asyncio.Event()
                    def on_frame(frame, elapsed, _q=frame_q, _f=first_ev):
                        data = pcm_bytes(frame)
                        loop.call_soon_threadsafe(_q.put_nowait, data)
                        if not _f.is_set(): loop.call_soon_threadsafe(_f.set)
                    job = worker.submit([ch], mf, body.voice_profile,
                                        job_class=JobClass.CALL_FIRST if idx == 0 else JobClass.CALL_CONT,
                                        mode=CALL_MODE, on_chunk=on_frame)
                    job.chunk_texts = [ch]
                    job.future.add_done_callback(lambda _fut, _q=frame_q: loop.call_soon_threadsafe(_q.put_nowait, None))
                    try: await asyncio.wait_for(first_ev.wait(), timeout=30)
                    except Exception: pass
                    return job, frame_q, mf

                next_idx = 0
                current = asyncio.create_task(run_one(next_idx, chunks[next_idx])); next_idx += 1
                prefetched = asyncio.create_task(run_one(next_idx, chunks[next_idx])) if next_idx < len(chunks) else None
                if prefetched: next_idx += 1
                idx = 0
                while idx < len(chunks):
                    job, frame_q, mf = await current
                    bufs = []
                    while True:
                        d = await frame_q.get()
                        if d is None: break
                        bufs.append(np.frombuffer(d, dtype='<i2').astype(np.float32) / 32768.0)
                    audio = await asyncio.wrap_future(job.future)
                    arr = np.concatenate(bufs) if bufs else (audio[0].detach().float().cpu().numpy() if hasattr(audio[0], 'detach') else np.asarray(audio[0], dtype=np.float32))
                    cap_hit = bool(getattr(job, 'cap_hit', False))
                    chunk_meta.append({"index": idx, "text": chunks[idx], "frames_cap": mf, "cap_hit": cap_hit, "eos_reached": not cap_hit, "audio_sec": round(len(arr)/sr,4)})
                    if cap_hit: log.warning("CAP_HIT /tts/stream chunk=%s frames=%s text=%r", idx, mf, chunks[idx])
                    a, prev_rms = smooth_chunk(arr, sr=sr, is_first=(idx==0), is_last=(idx==len(chunks)-1), prev_rms=prev_rms)
                    # determine pause by punctuation
                    txt = chunks[idx].rstrip()
                    pause_ms = 200 if re.search(r'[.?!]$', txt) else (100 if re.search(r'[,;:]$', txt) else 20)
                    if idx > 0:
                        cf = min(len(prev_tail), len(a), int(sr * 0.02))
                        if cf > 1:
                            w = np.linspace(1.0, 0.0, cf, dtype=np.float32)
                            cross = prev_tail[-cf:] * w + a[:cf] * (1.0 - w)
                            send = np.concatenate([prev_tail[:-cf], cross]) if len(prev_tail) > cf else cross
                            a = a[cf:]
                        else:
                            send = prev_tail
                        send = np.concatenate([send, np.zeros(int(sr * pause_ms / 1000), dtype=np.float32)])
                        if len(send) > holdback:
                            b=_yield_pcm(send[:-holdback]); 
                            if b: yield b
                            prev_tail = send[-holdback:]
                        else:
                            prev_tail = send
                    if len(a) > holdback:
                        out = a[:-holdback]
                        if idx == 0:
                            b=_yield_pcm(out); 
                            if b: yield b
                            prev_tail = a[-holdback:]
                        else:
                            prev_tail = np.concatenate([prev_tail, out]) if len(prev_tail) else out
                            if len(prev_tail) > holdback:
                                b=_yield_pcm(prev_tail[:-holdback]); 
                                if b: yield b
                                prev_tail = prev_tail[-holdback:]
                    else:
                        prev_tail = np.concatenate([prev_tail, a]) if idx > 0 else a
                    idx += 1
                    if prefetched is not None:
                        current = prefetched
                        prefetched = asyncio.create_task(run_one(next_idx, chunks[next_idx])) if next_idx < len(chunks) else None
                        if prefetched: next_idx += 1
                    elif idx < len(chunks):
                        current = asyncio.create_task(run_one(idx, chunks[idx])); next_idx = idx + 1
                    else:
                        break
                b=_yield_pcm(prev_tail, final=True)
                if b: yield b
                _assert_text_integrity(body.text, [m["text"] for m in chunk_meta])
            finally:
                job = state.get("job")
                if job is not None: job.stop.set()
                if call_mode: worker.exit_call()

        if call_mode:
            worker.enter_call()
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

    @app.websocket("/ws/tts")
    async def ws_tts(ws: WebSocket) -> None:
        await ws.accept()
        loop = asyncio.get_running_loop()
        cache: ChunkCache = app.state.chunk_cache
        state: dict[str, Any] = {"profile": None, "started": False, "cancelled": False}
        try:
            while True:
                msg = await ws.receive_json()
                action = msg.get("type") or msg.get("action")
                if action == "start":
                    profile = msg.get("voice_profile") or msg.get("voice")
                    if profile is not None and not getattr(
                        engine, "has_profile", lambda _: False
                    )(profile):
                        await ws.send_json(
                            {"event": "error", "detail": "unknown voice profile"}
                        )
                        continue
                    state["profile"] = profile
                    state["started"] = True
                    state["cancelled"] = False
                    worker.enter_call()
                    await ws.send_json({"event": "started"})
                elif action == "text":
                    if not state["started"]:
                        await ws.send_json({"event": "error", "detail": "send start first"})
                        continue
                    text = str(msg.get("text") or "").strip()
                    if not text:
                        await ws.send_json({"event": "error", "detail": "empty text"})
                        continue
                    profile = state["profile"]
                    max_frames = int(msg.get("max_frames") or settings.max_frames)
                    first_only = bool(msg.get("first_only"))
                    t_recv_ns = time.perf_counter_ns()
                    sent_ns = msg.get("sent_ns")
                    send_to_recv = None
                    if sent_ns:
                        send_to_recv = (time.time_ns() - int(sent_ns)) / 1e6
                    stream = engine._stream_for(profile)
                    requested = int(msg.get("first_max_frames") or 0)
                    est = estimate_first_max_frames(stream, text)
                    first_frames = requested if requested > 0 else int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES", str(est)))
                    first_frames = max(16, min(first_frames, max_frames))
                    cont_frames = min(
                        int(os.getenv("ARSENAL_CALL_CONT_MAX_FRAMES", "192")), max_frames
                    )
                    chunks = await loop.run_in_executor(
                        _CHUNK_POOL,
                        cache.get_or_split,
                        (text, first_frames),
                        lambda: split_call_text(stream, text, first_frames),
                    )
                    chunk_meta = []
                    total_samples = 0
                    for index, chunk in enumerate(chunks):
                        if state["cancelled"]:
                            break
                        cls = JobClass.CALL_FIRST if index == 0 else JobClass.CALL_CONT
                        est_chunk = estimate_first_max_frames(engine._stream_for(profile), chunk)
                        frames = max(24, min(int(est_chunk), max_frames)) if index == 0 else max(24, min(int(estimate_first_max_frames(engine._stream_for(profile), chunk)), max_frames))
                        # tokens*3+16 policy - generous, no truncation
                        t_submit_ns = time.perf_counter_ns()
                        frame_q: asyncio.Queue = asyncio.Queue()
                        def on_frame(frame: Any, elapsed: float, _q=frame_q) -> None:
                            data = pcm_bytes(frame)
                            loop.call_soon_threadsafe(_q.put_nowait, data)
                        try:
                            job = worker.submit(
                                [chunk], frames, profile,
                                job_class=cls, mode=CALL_MODE, on_chunk=on_frame,
                            )
                            job.t["handler"] = t_recv_ns
                            job.t["submit"] = t_submit_ns
                            job.t["ws"] = 1
                            job.chunk_texts = [chunk]
                            if index == 0:
                                metrics.record_ws_timing((t_submit_ns - t_recv_ns) / 1e6, None, send_to_recv)
                        except QueueFull:
                            await ws.send_json({"event": "error", "detail": "queue is full"})
                            break
                        await ws.send_json({"event": "chunk_start", "index": index, "frames": frames, "text": chunk})
                        t_job_ns = time.perf_counter_ns()
                        job.future.add_done_callback(lambda _f, _q=frame_q: loop.call_soon_threadsafe(_q.put_nowait, None))
                        samples = 0
                        first_sent_ns = None
                        comp = StreamPauseCompressor(sr=settings.sample_rate, holdback_ms=50)
                        async def _send_pcm(arr):
                            nonlocal first_sent_ns, samples
                            if arr.size == 0: return
                            pcm = (np.clip(arr,-1,1)*32767).astype('<i2').tobytes()
                            await ws.send_bytes(pcm)
                            if first_sent_ns is None:
                                first_sent_ns = time.perf_counter_ns()
                                job.t["first_byte_sent"] = first_sent_ns
                                emit_ns = job.t.get("first_emit")
                                after_emit = (first_sent_ns - emit_ns) / 1e6 if emit_ns else None
                                if index == 0:
                                    metrics.record_ws_phase((first_sent_ns - t_job_ns) / 1e6, 0.0, 0.0, after_emit)
                            samples += len(pcm) // 2
                        while True:
                            data = await frame_q.get()
                            if data is None:
                                break
                            arr = np.frombuffer(data, dtype='<i2').astype(np.float32) / 32768.0
                            out = comp.push(arr, final=False)
                            await _send_pcm(out)
                        tail = comp.push(np.zeros(0,dtype=np.float32), final=True)
                        await _send_pcm(tail)
                        audio = await asyncio.wrap_future(job.future)
                        if index == 0:
                            metrics.record_ws_timing(None, (time.perf_counter_ns() - t_recv_ns) / 1e6, None)
                        audio_sec = samples / float(settings.sample_rate)
                        cap_hit = bool(getattr(job, "cap_hit", False))
                        meta = {"index": index, "text": chunk, "frames_cap": frames, "cap_hit": cap_hit,
                                "eos_reached": not cap_hit, "audio_sec": round(audio_sec, 4), "samples": samples}
                        chunk_meta.append(meta)
                        total_samples += samples
                        if cap_hit:
                            log.warning("CAP_HIT chunk=%s frames=%s text=%r", index, frames, chunk)
                        await ws.send_json({"event": "chunk_done", **meta})
                        if first_only:
                            break
                    try:
                        _assert_text_integrity(text, [m["text"] for m in chunk_meta])
                    except Exception as e:
                        await ws.send_json({"event": "error", "detail": str(e)})
                        log.error("text integrity: %s", e)
                    await ws.send_json({"event": "utterance_done", "chunks": chunk_meta, "total_audio_sec": round(total_samples/float(settings.sample_rate),4)})
                elif action == "flush":
                    await ws.send_json({"event": "flushed"})
                    await ws.close()
                    return
                elif action == "cancel":
                    state["cancelled"] = True
                    await ws.send_json({"event": "cancelled"})
                else:
                    await ws.send_json({"event": "error", "detail": "unknown action"})
        except WebSocketDisconnect:
            pass
        finally:
            if state["started"]:
                state["started"] = False
                worker.exit_call()

    def _debug_guard() -> None:
        if os.getenv("ARSENAL_DEBUG") != "1":
            raise HTTPException(status_code=404, detail="not found")

    async def _wait_drained(timeout_s: float = 60.0, empty_cache: bool = False) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if worker.depth == 0 and worker.active_call_sessions == 0:
                if empty_cache:
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                return {"drained": True, "queue_depth": 0, "active_call_sessions": 0}
            await asyncio.sleep(0.02)
        return {
            "drained": False,
            "queue_depth": worker.depth,
            "active_call_sessions": worker.active_call_sessions,
        }

    @app.get("/debug/drain")
    async def debug_drain(timeout: float = 60.0, empty_cache: int = 0) -> dict[str, Any]:
        _debug_guard()
        return await _wait_drained(timeout_s=timeout, empty_cache=bool(empty_cache))

    def _call_text() -> str:
        return (
            "Hello, this is a call from Arsenal. "
            "The quick brown fox jumps over the lazy dog. "
            "Pack my box with five dozen liquor jugs."
        )

    async def _one_call(
        profile: str | None,
        first_frames: int,
        cont_frames: int,
        cancel: bool = False,
        first_only: bool = False,
        text: str | None = None,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        text = text or _call_text()
        stream = engine._stream_for(profile)
        cache: ChunkCache = app.state.chunk_cache
        chunks = await loop.run_in_executor(
            _CHUNK_POOL,
            cache.get_or_split,
            (text, first_frames),
            lambda: split_call_text(stream, text, first_frames),
        )
        worker.enter_call()
        t0 = time.monotonic()
        t0_ns = time.perf_counter_ns()
        first_ms: float | None = None
        first_byte_ms: float | None = None
        timing: dict[str, Any] = {}
        try:
            for index, chunk in enumerate(chunks):
                if first_only and index > 0:
                    break
                cls = JobClass.CALL_FIRST if index == 0 else JobClass.CALL_CONT
                frames = first_frames if index == 0 else cont_frames
                got = {"t": None}

                def on_chunk(frame: Any, elapsed: float) -> None:
                    if got["t"] is None:
                        got["t"] = time.monotonic()

                job = worker.submit(
                    [chunk],
                    frames,
                    profile,
                    job_class=cls,
                    mode=CALL_MODE,
                    on_chunk=on_chunk,
                )
                if cancel and index == 0:
                    job.cancelled = True
                    job.stop.set()
                    try:
                        await asyncio.wrap_future(job.future)
                    except BaseException:
                        pass
                    return {"cancelled": True}
                await asyncio.wrap_future(job.future)
                if index == 0:
                    first_ms = (time.monotonic() - t0) * 1000.0
                    if got["t"] is not None:
                        first_byte_ms = (got["t"] - t0) * 1000.0
                    timing = {
                        "submit_ms": (job.t.get("submit", 0) - t0_ns) / 1e6 if job.t.get("submit") else None,
                        "batch_start_ms": (job.t.get("batch_start", 0) - t0_ns) / 1e6 if job.t.get("batch_start") else None,
                        "first_emit_ms": (job.t.get("first_emit", 0) - t0_ns) / 1e6 if job.t.get("first_emit") else None,
                    }
        finally:
            worker.exit_call()
        return {"first_ms": first_ms, "first_byte_ms": first_byte_ms, "timing": timing}

    async def _one_normal(profile: str | None, frames: int) -> float:
        t0 = time.monotonic()
        job = worker.submit(["normal load test"], frames, profile)
        await asyncio.wrap_future(job.future)
        return (time.monotonic() - t0) * 1000.0

    @app.get("/debug/callramp")
    async def debug_callramp(request: Request) -> dict[str, Any]:
        _debug_guard()
        qp = request.query_params
        b = int(qp.get("b", "224"))
        repeats = max(1, int(qp.get("repeats", "1")))
        first_frames = int(qp.get("first_max_frames", "0")) or int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES","24"))
        cont_frames = int(qp.get("cont_max_frames", "192"))
        profile = qp.get("profile") or None
        first_only = qp.get("first_only", "0") == "1"
        text = qp.get("text") or None
        window = qp.get("window")
        if window is not None:
            os.environ["ARSENAL_BATCH_WINDOW_MS"] = str(int(window))
        worker.reload_config()
        runs = []
        for _ in range(repeats):
            drained_before = await _wait_drained(timeout_s=120.0, empty_cache=True)
            before = _vram_mb()
            bs0 = list(metrics.batch_size)
            results = await asyncio.gather(
                *[
                    _one_call(
                        profile,
                        first_frames,
                        cont_frames,
                        first_only=first_only,
                        text=text,
                    )
                    for _ in range(b)
                ],
                return_exceptions=True,
            )
            items = [r for r in results if isinstance(r, dict)]
            firsts = [r["first_ms"] for r in items if r.get("first_ms") is not None]
            bytes_ms = [
                r["first_byte_ms"] for r in items if r.get("first_byte_ms") is not None
            ]
            errors = sum(1 for r in results if isinstance(r, BaseException))
            def tstat(key):
                vals=[it.get("timing",{}).get(key) for it in items]
                vals=[v for v in vals if isinstance(v,(int,float))]
                return _stats_list(vals)
            runs.append(
                {
                    "first_chunk_ms": _stats_list(firsts),
                    "first_byte_ms": _stats_list(bytes_ms),
                    "timing_submit_ms": tstat("submit_ms"),
                    "timing_batch_start_ms": tstat("batch_start_ms"),
                    "timing_first_emit_ms": tstat("first_emit_ms"),
                    "batch_sizes": list(metrics.batch_size)[len(bs0):],
                    "errors": errors,
                    "vram_mb": {"before": before, "after": _vram_mb()},
                    "drained_before": drained_before,
                    "drained_after": await _wait_drained(timeout_s=120.0, empty_cache=True),
                }
            )
        return {"b": b, "runs": runs, "ok": all(r["errors"] == 0 for r in runs)}

    @app.get("/debug/callmixed")
    async def debug_callmixed(request: Request) -> dict[str, Any]:
        _debug_guard()
        qp = request.query_params
        calls = int(qp.get("call", "128"))
        normals = int(qp.get("normal", "32"))
        first_frames = int(qp.get("first_max_frames", "0")) or int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES","24"))
        cont_frames = int(qp.get("cont_max_frames", "192"))
        profile = qp.get("profile") or None
        first_only = qp.get("first_only", "1") == "1"
        drained_before = await _wait_drained(timeout_s=120.0, empty_cache=True)
        call_tasks = [
            _one_call(
                profile,
                first_frames,
                cont_frames,
                first_only=first_only,
            )
            for _ in range(calls)
        ]
        normal_tasks = [_one_normal(profile, cont_frames) for _ in range(normals)]
        results = await asyncio.gather(
            *call_tasks, *normal_tasks, return_exceptions=True
        )
        call_results = results[:calls]
        normal_results = results[calls:]
        call_items = [r for r in call_results if isinstance(r, dict)]
        call_first = [r["first_ms"] for r in call_items if r.get("first_ms") is not None]
        call_first_byte = [
            r["first_byte_ms"] for r in call_items if r.get("first_byte_ms") is not None
        ]
        normal_ms = [r for r in normal_results if isinstance(r, (int, float))]
        errors = sum(1 for r in results if isinstance(r, BaseException))
        return {
            "call_first_ms": _stats_list(call_first),
            "call_first_byte_ms": _stats_list(call_first_byte),
            "normal_ms": _stats_list(normal_ms),
            "errors": errors,
            "ok": errors == 0,
            "drained_before": drained_before,
            "drained_after": await _wait_drained(timeout_s=120.0, empty_cache=True),
        }

    @app.get("/debug/callcancel")
    async def debug_callcancel(request: Request) -> dict[str, Any]:
        _debug_guard()
        qp = request.query_params
        b = int(qp.get("b", "128"))
        cancel_frac = float(qp.get("cancel_frac", "0.5"))
        first_frames = int(qp.get("first_max_frames", "0")) or int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES","24"))
        cont_frames = int(qp.get("cont_max_frames", "192"))
        profile = qp.get("profile") or None
        cancelled = int(b * cancel_frac)
        drained_before = await _wait_drained(timeout_s=120.0, empty_cache=True)
        before = _vram_mb()
        await asyncio.gather(
            *[
                _one_call(
                    profile,
                    first_frames,
                    cont_frames,
                    cancel=index < cancelled,
                    first_only=True,
                )
                for index in range(b)
            ],
            return_exceptions=True,
        )
        after = _vram_mb()
        return {
            "active_call_sessions": worker.active_call_sessions,
            "queue_depth": worker.depth,
            "vram_mb": {"before": before, "after": after},
            "drained_before": drained_before,
            "drained_after": await _wait_drained(timeout_s=120.0, empty_cache=True),
            "ok": worker.active_call_sessions == 0 and worker.depth == 0,
        }

    @app.get("/debug/vram")
    def debug_vram() -> dict[str, Any]:
        if os.getenv("ARSENAL_DEBUG") != "1":
            raise HTTPException(status_code=404, detail="not found")
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                return {
                    "allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 1),
                    "reserved_mb": round(torch.cuda.memory_reserved() / (1024 * 1024), 1),
                    "max_allocated_mb": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1),
                }
        except Exception as e:
            return {"error": str(e)}
        return {"error": "no cuda"}

    @app.get("/debug/selfprobe")
    async def debug_selfprobe(
        b: int = 32,
        bursts: int = 3,
        window: int = 150,
        target: int = 224,
        profile: str | None = None,
        max_frames: int = 192,
        empty_cache: int = 0,
    ) -> dict[str, Any]:
        if os.getenv("ARSENAL_DEBUG") != "1":
            raise HTTPException(status_code=404, detail="not found")
        import httpx
        from httpx import ASGITransport

        def _pct(values: list[float], p: float) -> float | None:
            if not values:
                return None
            ordered = sorted(values)
            k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
            return round(ordered[k], 2)

        os.environ["ARSENAL_BATCH_WINDOW_MS"] = str(window)
        os.environ["ARSENAL_BATCH_TARGET"] = str(target)
        texts = [
            "A short test line for the TTS benchmark.",
            "This is a longer line to keep the batch worker busy while we measure first byte timing under burst load.",
            "Another example sentence that should produce several audio frames and exercise the worker queue.",
            "Short one.",
        ]
        metrics.reset()
        transport = ASGITransport(app=app)
        all_first: list[float] = []
        errors = 0
        async with httpx.AsyncClient(transport=transport, base_url="http://self") as client:
            for bi in range(bursts):
                if empty_cache:
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                bid = f"self-{bi}-{b}-{time.time_ns()}"
                async def one(i: int, _bid: str = bid) -> tuple[int, float | None]:
                    body: dict[str, Any] = {"text": texts[i % len(texts)], "max_frames": max_frames}
                    if profile:
                        body["voice_profile"] = profile
                    headers = {"x-burst-id": _bid, "x-sent-at": str(time.time_ns())}
                    start = time.perf_counter()
                    first: float | None = None
                    try:
                        async with client.stream(
                            "POST", "/tts/stream", json=body, headers=headers, timeout=300.0
                        ) as r:
                            status = r.status_code
                            async for _ in r.aiter_bytes():
                                if first is None:
                                    first = (time.perf_counter() - start) * 1000.0
                            if status == 200 and first is None:
                                first = (time.perf_counter() - start) * 1000.0
                            return status, first
                    except Exception:
                        return 0, None

                results = await asyncio.gather(*(one(i) for i in range(b)))
                for status, first in results:
                    if status != 200 or first is None:
                        errors += 1
                    else:
                        all_first.append(first)
        snap = metrics.snapshot()
        return {
            "b": b,
            "bursts": bursts,
            "window": window,
            "target": target,
            "profile": profile,
            "max_frames": max_frames,
            "client": {
                "p50_ms": _pct(all_first, 50),
                "p95_ms": _pct(all_first, 95),
                "errors": errors,
                "n": len(all_first),
            },
            "server": snap,
        }

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
