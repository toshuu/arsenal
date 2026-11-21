"""Stream-time near-silence gap compression for call mode."""

from __future__ import annotations

import os
import numpy as np


def compress_long_pauses(
    audio,
    sr: int = 24000,
    max_pause_ms: int = 250,
    target_ms: int = 250,
    guard_ms: int = 40,
    fade_ms: int = 18,
    thr: float = 0.01,
    compress_trailing: bool = True,
):
    if max_pause_ms <= 0:
        return np.asarray(audio, dtype=np.float32)
    a = np.asarray(audio, dtype=np.float32).reshape(-1).copy()
    if a.size == 0:
        return a
    guard = int(sr * guard_ms / 1000)
    fade_n = int(sr * fade_ms / 1000)
    target = int(sr * max(target_ms, 120) / 1000)
    max_pause = int(sr * max_pause_ms / 1000)
    sil = np.abs(a) < thr
    out = []
    i = 0
    n = len(a)
    while i < n:
        if not sil[i]:
            j = i
            while j < n and not sil[j]:
                j += 1
            out.append(a[i:j])
            i = j
            continue
        j = i
        while j < n and sil[j]:
            j += 1
        gap_len = j - i
        at_end = j >= n
        # if at end of non-final buffer, compress only if clearly over limit (voice follows in holdback)
        if gap_len <= max_pause or (at_end and not compress_trailing and gap_len <= max_pause):
            out.append(a[i:j])
            i = j
            continue
        if at_end and not compress_trailing and gap_len > max_pause:
            # compress but keep only left+mid; right side continues in holdback/next
            left = min(guard, gap_len // 2)
            mid_keep = max(0, target - left)
            seg = np.concatenate([a[i:i+left], np.zeros(mid_keep, dtype=np.float32)]) if left < gap_len else a[i:j]
            if fade_n > 1 and len(seg) > fade_n:
                w = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
                seg[:fade_n] *= 1.0 - w
            out.append(seg)
            i = j
            continue
        left = min(guard, gap_len // 2)
        right = min(guard, gap_len - left)
        mid_keep = max(0, target - left - right)
        seg = np.concatenate([
            a[i:i + left],
            np.zeros(mid_keep, dtype=np.float32),
            a[j - right:j],
        ]) if (left + right) < gap_len else a[i:j]
        if fade_n > 1 and len(seg) > fade_n * 2:
            w = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
            seg[:fade_n] *= 1.0 - w
            seg[-fade_n:] *= w
        out.append(seg)
        i = j
    return np.concatenate(out) if out else a


class StreamPauseCompressor:
    """Online compressor. Hold trailing silence until voice closes it; compress closed gaps."""

    def __init__(self, sr=24000, max_pause_ms=None, target_ms=None, holdback_ms=60):
        env = os.getenv("ARSENAL_CALL_PAUSE_MAX_MS")
        mpm = int(env) if env is not None and env != "" else (250 if max_pause_ms is None else int(max_pause_ms))
        self.max_pause_ms = mpm
        self.target_ms = 250 if target_ms is None else int(target_ms)
        self.sr = sr
        self.holdback = int(sr * holdback_ms / 1000)
        self.thr = 0.01
        self.buf = np.zeros(0, dtype=np.float32)

    def push(self, chunk, final=False):
        a = np.asarray(chunk, dtype=np.float32).reshape(-1)
        if a.size:
            self.buf = np.concatenate([self.buf, a]) if self.buf.size else a
        if self.buf.size == 0:
            return np.zeros(0, dtype=np.float32)
        if final:
            proc = self.buf
            self.buf = np.zeros(0, dtype=np.float32)
            return compress_long_pauses(proc, sr=self.sr, max_pause_ms=self.max_pause_ms, target_ms=self.target_ms, thr=self.thr, compress_trailing=True)

        sil = np.abs(self.buf) < self.thr
        if sil[-1]:
            return np.zeros(0, dtype=np.float32)

        if len(self.buf) <= self.holdback:
            return np.zeros(0, dtype=np.float32)
        proc = self.buf[:-self.holdback]
        self.buf = self.buf[-self.holdback:]
        return compress_long_pauses(proc, sr=self.sr, max_pause_ms=self.max_pause_ms, target_ms=self.target_ms, thr=self.thr, compress_trailing=False)
