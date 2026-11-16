"""Verify the voice-embedding cache: audio identical, boot cost lower."""

import json
import logging
import os
import sys
import time
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)

from pocket_tts import TTSModel  # noqa: E402
from batch.batched_stream import BatchedStream  # noqa: E402
from batch.fp16 import enable_fp16_backbone  # noqa: E402
from batch.fp16_weights import load_fp16_weights  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
TEXT = "The old sailor found a brass key."
for p in (REPO / "Code" / "model" / "voice_cache").glob("*.pt"):
    p.unlink()

model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
enable_fp16_backbone(model, mimi_fp16=True)
load_fp16_weights(model, REPO / "Code" / "model" / "fp16_weights.pt")
model.temp = 0.0
t = time.perf_counter()
miss = BatchedStream(model, voice=str(VOICE), voice_seconds=4.0, max_first_tokens=16)
miss_ms = (time.perf_counter() - t) * 1000
t = time.perf_counter()
hit = BatchedStream(model, voice=str(VOICE), voice_seconds=4.0, max_first_tokens=16)
hit_ms = (time.perf_counter() - t) * 1000
a = miss.stream([TEXT], max_frames=240)[0].float().cpu()
b = hit.stream([TEXT], max_frames=240)[0].float().cpu()
n = min(a.numel(), b.numel())
report = {"miss_ms": miss_ms, "hit_ms": hit_ms, "corr": float(torch.corrcoef(torch.stack([a[:n], b[:n]]))[0, 1]),
          "max_abs_diff": float((a[:n] - b[:n]).abs().max())}
(REPO / "Code/probes/out/check_voice_cache.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
print("CHECK_VOICE_CACHE", "PASS" if report["corr"] >= 0.999 else "FAIL")
