"""Measure T4 memory at the B=224 long-frame limit."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.getenv("ARSENAL_POCKET_TTS"):
    sys.path.insert(0, os.environ["ARSENAL_POCKET_TTS"])
os.chdir(ROOT / "model")
logging.disable(logging.CRITICAL)

import torch

from pocket_tts import TTSModel

from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights

OUT = ROOT / "probes" / "out" / "probe_long_frame_capacity.json"
VOICE = str(ROOT / "probes" / "ref" / "voice.wav")
BATCH = int(os.getenv("ARSENAL_CAP_BATCH", "224"))
FRAMES = int(os.getenv("ARSENAL_CAP_FRAMES", "192"))


def main() -> int:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    model.temp = 0.0
    enable_fp16_backbone(model, mimi_fp16=True)
    weights = Path("fp16_weights.pt")
    if weights.exists():
        load_fp16_weights(model, weights)
    base = BatchedStream(
        model,
        voice=VOICE,
        voice_seconds=4.0,
        max_first_tokens=16,
        max_allowed_frames=FRAMES,
    )
    profile = Path(tempfile.gettempdir()) / "arsenal_cap_profile.pt"
    base.save_voice_profile(profile, conditioned=True)
    stream = BatchedStream(
        model,
        voice_profile=profile,
        max_first_tokens=16,
        max_allowed_frames=FRAMES,
    )
    texts = ["Hello there."] * BATCH
    torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    audio = stream.stream(texts, max_frames=FRAMES)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    result = {
        "gpu": torch.cuda.get_device_name(0),
        "batch": BATCH,
        "max_frames": FRAMES,
        "seconds": round(elapsed, 3),
        "peak_alloc_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
        "peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 3),
        "free_gib": round(torch.cuda.mem_get_info()[0] / 2**30, 3),
        "rows": len(audio),
        "all_nonempty": all(a.numel() > 0 for a in audio),
    }
    result["ok"] = bool(result["all_nonempty"] and result["free_gib"] >= 1.0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
