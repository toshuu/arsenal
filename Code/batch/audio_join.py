"""Lightweight join smoothing for call-mode chunk audio."""

from __future__ import annotations

import numpy as np


def _as_f32(x):
    a = np.asarray(x, dtype=np.float32).reshape(-1)
    return np.clip(a, -1.0, 1.0)


def trim_trailing_silence(audio, sr=24000, thresh=0.01, keep_ms=120, min_ms=80):
    a = _as_f32(audio)
    if a.size == 0:
        return a
    idx = np.where(np.abs(a) > thresh)[0]
    if len(idx) == 0:
        return a[: int(sr * min_ms / 1000)]
    end = int(idx[-1]) + 1
    keep = int(sr * keep_ms / 1000)
    end = min(len(a), end + keep)
    end = max(end, int(sr * min_ms / 1000))
    return a[:end]


def trim_leading_silence(audio, sr=24000, thresh=0.01, keep_ms=30):
    a = _as_f32(audio)
    idx = np.where(np.abs(a) > thresh)[0]
    if len(idx) == 0:
        return a
    start = max(0, int(idx[0]) - int(sr * keep_ms / 1000))
    return a[start:]


def fade(audio, sr=24000, ms_in=10, ms_out=20):
    a = _as_f32(audio).copy()
    n_in = min(len(a), int(sr * ms_in / 1000))
    n_out = min(len(a), int(sr * ms_out / 1000))
    if n_in > 1:
        a[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
    if n_out > 1:
        a[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)
    return a


def normalize_rms(audio, target_rms=0.08, max_gain=3.0):
    a = _as_f32(audio).copy()
    r = float(np.sqrt(np.mean(a * a) + 1e-12))
    if r < 1e-6:
        return a
    g = min(max_gain, target_rms / r)
    return np.clip(a * g, -1.0, 1.0)


def smooth_chunk(audio, sr=24000, is_first=False, is_last=False, prev_rms=None):
    a = trim_leading_silence(audio, sr=sr) if is_first else trim_leading_silence(audio, sr=sr, keep_ms=10)
    a = trim_trailing_silence(a, sr=sr, keep_ms=140 if is_last else 90)
    # loudness match gently toward previous
    target = 0.08
    if prev_rms is not None and prev_rms > 1e-4:
        target = float(np.clip(prev_rms, 0.04, 0.12))
    a = normalize_rms(a, target_rms=target, max_gain=2.5)
    a = fade(a, sr=sr, ms_in=5 if is_first else 12, ms_out=25 if is_last else 15)
    cur_rms = float(np.sqrt(np.mean(a * a) + 1e-12))
    return a, cur_rms


def join_chunks(chunks, sr=24000, pause_ms=60):
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    out = []
    prev_rms = None
    pause = np.zeros(int(sr * pause_ms / 1000), dtype=np.float32)
    for i, ch in enumerate(chunks):
        a, prev_rms = smooth_chunk(ch, sr=sr, is_first=i == 0, is_last=i == len(chunks) - 1, prev_rms=prev_rms)
        if i > 0:
            # short crossfade with pause tail/head
            cf = min(len(out[-1]), len(a), int(sr * 0.02))
            if cf > 1:
                w = np.linspace(1.0, 0.0, cf, dtype=np.float32)
                out[-1][-cf:] = out[-1][-cf:] * w + a[:cf] * (1.0 - w)
                a = a[cf:]
            out.append(pause.copy())
        out.append(a)
    return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
