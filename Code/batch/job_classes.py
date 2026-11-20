"""Job classes and class-aware batch selection for the TTS server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from queue import Empty
from typing import Any


class JobClass(str, Enum):
    CALL_FIRST = "call_first"
    CALL_CONT = "call_cont"
    NORMAL = "normal"


PRIORITY = {
    JobClass.CALL_FIRST: 0,
    JobClass.CALL_CONT: 1,
    JobClass.NORMAL: 2,
}


@dataclass(frozen=True)
class ClassConfig:
    cls: JobClass
    max_batch: int
    max_frames: int
    window_ms: int


@dataclass(frozen=True)
class Config:
    classes: dict[JobClass, ClassConfig]
    normal_busy_max_batch: int
    normal_busy_max_frames: int
    max_rows: int


def _int(env: Any, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def load_class_config(env: Any = None) -> Config:
    if env is None:
        env = os.environ
    specs = (
        (JobClass.CALL_FIRST, "CALL_FIRST", 32, 224),
        (JobClass.CALL_CONT, "CALL_CONT", 192, 224),
        (JobClass.NORMAL, "NORMAL", 192, 192),
    )
    default_window = _int(env, "ARSENAL_BATCH_WINDOW_MS", 150)
    classes: dict[JobClass, ClassConfig] = {}
    for cls, prefix, frame_default, batch_default in specs:
        frames = _int(env, f"ARSENAL_{prefix}_MAX_FRAMES", frame_default)
        batch = _int(env, f"ARSENAL_{prefix}_MAX_BATCH", batch_default)
        window = _int(env, f"ARSENAL_{prefix}_WINDOW_MS", default_window)
        classes[cls] = ClassConfig(cls, batch, frames, window)
    return Config(
        classes=classes,
        normal_busy_max_batch=_int(env, "ARSENAL_NORMAL_BUSY_MAX_BATCH", 4),
        normal_busy_max_frames=_int(env, "ARSENAL_NORMAL_BUSY_MAX_FRAMES", 64),
        max_rows=_int(env, "ARSENAL_MAX_ROWS", 224),
    )


def select_class(queues: dict[JobClass, Any], active_sessions: int = 0) -> JobClass | None:
    for cls in (JobClass.CALL_FIRST, JobClass.CALL_CONT, JobClass.NORMAL):
        q = queues.get(cls)
        if q is not None and not q.empty():
            return cls
    return None


def normal_limits(cfg: Config, active_sessions: int) -> tuple[int, int]:
    limit = cfg.classes[JobClass.NORMAL].max_batch
    frames = cfg.classes[JobClass.NORMAL].max_frames
    if active_sessions > 0:
        limit = min(limit, cfg.normal_busy_max_batch)
        frames = min(frames, cfg.normal_busy_max_frames)
    return limit, frames


def select_batch(
    queues: dict[JobClass, Any], cfg: Config, active_sessions: int = 0
) -> tuple[JobClass | None, list[Any]]:
    cls = select_class(queues, active_sessions)
    if cls is None:
        return None, []
    limit = cfg.classes[cls].max_batch
    if cls is JobClass.NORMAL:
        limit, _ = normal_limits(cfg, active_sessions)
    q = queues[cls]
    batch: list[Any] = []
    rows = 0
    while len(batch) < limit and rows < cfg.max_rows:
        try:
            job = q.get_nowait()
        except Empty:
            break
        if getattr(job, "cancelled", False):
            continue
        n = len(job.texts)
        if rows + n > cfg.max_rows:
            q.put_nowait(job)
            break
        batch.append(job)
        rows += n
    if not batch:
        return None, []
    return cls, batch
