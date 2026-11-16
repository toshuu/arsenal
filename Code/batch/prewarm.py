"""Bounded prewarm for the first decode shapes."""

from __future__ import annotations

import torch


def prewarm(stream, texts: list[str], batch: int | None = None, max_frames: int = 1) -> None:
    """Run one short batch through the full path and sync the GPU."""
    n = min(len(texts), batch) if batch else len(texts)
    stream.stream(texts[:n], max_frames=max_frames)
    torch.cuda.synchronize()
