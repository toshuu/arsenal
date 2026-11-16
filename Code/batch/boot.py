"""Boot-time prewarm switch for the container entrypoint."""

from __future__ import annotations

import os


def prewarm_config() -> tuple[bool, int, int]:
    flag = os.getenv("ARSENAL_PREWARM", "1").strip().lower()
    enabled = flag not in ("0", "false", "off", "no")
    batch = int(os.getenv("ARSENAL_PREWARM_B", "192"))
    frames = int(os.getenv("ARSENAL_PREWARM_FRAMES", "1"))
    return enabled, batch, frames


def maybe_prewarm(stream, texts: list[str]) -> float:
    """Prewarm when enabled. Return the cost in ms."""
    import time

    from .prewarm import prewarm

    enabled, batch, frames = prewarm_config()
    if not enabled:
        return 0.0
    t = time.perf_counter()
    prewarm(stream, texts, batch=batch, max_frames=frames)
    return (time.perf_counter() - t) * 1000.0
