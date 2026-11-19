"""Measure audio joins between independently generated text chunks."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.getenv("ARSENAL_POCKET_TTS"):
    sys.path.insert(0, os.environ["ARSENAL_POCKET_TTS"])
os.chdir(ROOT / "model")
logging.disable(logging.CRITICAL)

import numpy as np
import torch

from pocket_tts import TTSModel

from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights

OUT = ROOT / "probes" / "out" / "check_chunk_joins.json"
VOICE = str(ROOT / "probes" / "ref" / "voice.wav")
TEXT = (
    "The quick brown fox jumps over the lazy dog near the river. "
    "A silver train leaves the station at noon every single day. "
    "Please close the windows before the storm arrives. "
    "The small boat moves slowly under the old stone bridge."
)


def load() -> tuple[object, BatchedStream]:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    model.temp = 0.0
    enable_fp16_backbone(model, mimi_fp16=True)
    weights = Path("fp16_weights.pt")
    if weights.exists():
        load_fp16_weights(model, weights)
    stream = BatchedStream(
        model,
        voice=VOICE,
        voice_seconds=4.0,
        max_first_tokens=16,
        max_allowed_frames=192,
    )
    return model, stream


def save_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def analyze(samples: np.ndarray, boundaries: list[int], rate: int) -> dict[str, object]:
    diff = np.abs(np.diff(samples))
    p999 = float(np.percentile(diff, 99.9)) if diff.size else 0.0
    rows = []
    for pos in boundaries:
        lo = max(0, pos - rate // 50)
        hi = min(diff.size, pos + rate // 50)
        join_jump = float(diff[pos - 1]) if 0 < pos <= diff.size else 0.0
        local = float(diff[lo:hi].max()) if hi > lo else 0.0
        before = float(np.sqrt(np.mean(samples[max(0, pos - rate // 50) : pos] ** 2)))
        after = float(np.sqrt(np.mean(samples[pos : min(samples.size, pos + rate // 50)] ** 2)))
        rows.append(
            {
                "at_s": round(pos / rate, 3),
                "join_jump": round(join_jump, 5),
                "local_max_jump": round(local, 5),
                "rms_before": round(before, 5),
                "rms_after": round(after, 5),
                "rms_ratio": round(after / before, 3) if before > 1e-6 else None,
            }
        )
    return {
        "p99_9_jump": round(p999, 5),
        "joins": rows,
        "no_click": all(r["join_jump"] <= max(0.05, p999 * 10) for r in rows),
        "no_rms_drop": all(
            r["rms_ratio"] is None or r["rms_ratio"] > 0.2 for r in rows
        ),
    }


def run_one(name: str, stream: BatchedStream, rate: int) -> dict[str, object]:
    chunks = stream._text_chunks(TEXT)
    audios = [stream.stream([chunk])[0].float().cpu().numpy() for chunk in chunks]
    full = np.concatenate(audios)
    boundaries = np.cumsum([len(a) for a in audios[:-1]]).astype(int).tolist()
    metrics = analyze(full, boundaries, rate)
    path = ROOT / "probes" / "out" / f"chunk_joins_{name}.wav"
    save_wav(path, full, rate)
    expected = [w for w in re.sub(r"[^\w]+", " ", TEXT.lower()).split() if w]
    actual = [w for w in re.sub(r"[^\w]+", " ", " ".join(chunks).lower()).split() if w]
    return {
        "chunks": len(chunks),
        "bytes": int(full.size * 2),
        "seconds": round(full.size / rate, 3),
        "boundaries_s": [round(b / rate, 3) for b in boundaries],
        "coverage_ok": expected == actual,
        "wav": str(path),
        **metrics,
    }


def main() -> int:
    model, normal = load()
    rate = model.config.mimi.sample_rate
    result: dict[str, object] = {}
    result["normal"] = run_one("normal", normal, rate)

    profile = Path(tempfile.gettempdir()) / "arsenal_join_profile.pt"
    normal.save_voice_profile(profile, conditioned=True)
    prof = BatchedStream(
        model,
        voice_profile=profile,
        max_first_tokens=16,
        max_allowed_frames=192,
    )
    result["profile"] = run_one("profile", prof, rate)
    result["ok"] = bool(
        result["normal"]["coverage_ok"]
        and result["profile"]["coverage_ok"]
        and result["normal"]["no_click"]
        and result["profile"]["no_click"]
        and Path(result["normal"]["wav"]).exists()
        and Path(result["profile"]["wav"]).exists()
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "normal": result["normal"]["chunks"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
