"""Parity and listening WAVs for pre-cast FP16 weights."""

import json
import logging
import os
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)

from pocket_tts import TTSModel  # noqa: E402
from batch.batched_stream import BatchedStream  # noqa: E402
from batch.fp16 import enable_fp16_backbone  # noqa: E402
from batch.fp16_weights import load_fp16_weights, save_fp16_weights  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
OUT = REPO / "Code" / "probes" / "out"
WEIGHTS = REPO / "Code" / "model" / "fp16_weights.pt"
TEXTS = [
    "The old sailor found a brass key.",
    "A young engineer found a brass key while the wind moved slowly near the library.",
    "Testing one two three four five six seven eight nine ten.",
]


def synth(weights: bool):
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=True)
    if weights:
        if not WEIGHTS.exists():
            save_fp16_weights(model, WEIGHTS)
        load_fp16_weights(model, WEIGHTS)
    else:
        save_fp16_weights(model, WEIGHTS)
    model.temp = 0.0
    stream = BatchedStream(model, voice=str(VOICE), voice_seconds=4.0,
                           max_first_tokens=16, compact=True)
    audio = stream.stream(TEXTS, max_frames=240)
    rows = [a.detach().float().cpu() for a in audio]
    sr = model.config.mimi.sample_rate
    del stream, model
    torch.cuda.empty_cache()
    return rows, sr


def main() -> int:
    base, sr = synth(False)
    half, _ = synth(True)
    rows = []
    for i, (a, b) in enumerate(zip(base, half)):
        n = min(a.numel(), b.numel())
        corr = float(torch.corrcoef(torch.stack([a[:n], b[:n]]))[0, 1])
        rows.append({"row": i, "corr": corr,
                     "max_abs_diff": float((a[:n] - b[:n]).abs().max())})
    OUT.mkdir(parents=True, exist_ok=True)
    import soundfile as sf

    gap = torch.zeros(int(0.5 * sr))
    mix = torch.cat([base[0], gap, half[0], gap])
    sf.write("/kaggle/working/fp16_weights_compare.wav", mix.numpy(), sr)
    report = {"rows": rows, "min_corr": min(r["corr"] for r in rows),
              "max_abs_diff": max(r["max_abs_diff"] for r in rows), "sr": sr}
    (OUT / "check_fp16_weights.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"min_corr": report["min_corr"],
                      "max_abs_diff": report["max_abs_diff"]}))
    ok = report["min_corr"] >= 0.999
    print("CHECK_FP16_WEIGHTS", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
