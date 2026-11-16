"""Parity check for FP16 Mimi decode (E2 of IDEA-0004).

Load one model with FP32 Mimi and one model with FP16 Mimi. Run the same
texts at temperature 0. Compare the waveforms.

Writes Code/probes/out/check_mimi_fp16.json and two WAVs.
Prints CHECK_MIMI_FP16 PASS or FAIL.
"""

import json
import logging
import os
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
sys.path.insert(0, str(REPO / "Code" / "probes"))
os.chdir(REPO / "Code" / "model")

logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel  # noqa: E402

from batch.batched_stream import BatchedStream  # noqa: E402
from batch.fp16 import enable_fp16_backbone  # noqa: E402
from bench_batch_server import make_texts  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
PROFILE = REPO / "Code" / "probes" / "out" / "voice_4s_cond.pt"
OUT = REPO / "Code" / "probes" / "out"


def run(mimi_fp16: bool, texts):
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=mimi_fp16)
    model.temp = 0.0
    stream = BatchedStream(
        model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16, compact=True
    )
    if not PROFILE.exists():
        stream.save_voice_profile(PROFILE, conditioned=True)
    stream = BatchedStream(
        model, voice_profile=PROFILE, max_first_tokens=16, compact=True
    )
    audio = stream.stream(texts, max_frames=32)
    result = [row.detach().float().cpu() for row in audio]
    sr = model.config.mimi.sample_rate
    del stream, model
    torch.cuda.empty_cache()
    return result, sr


def main():
    texts = make_texts(8)
    base, sr = run(False, texts)
    half, _ = run(True, texts)
    rows = []
    for i in range(len(base)):
        a, b = base[i], half[i]
        limit = min(a.numel(), b.numel())
        a, b = a[:limit], b[:limit]
        diff = float((a - b).abs().max()) if limit else None
        corr = None
        if limit > 1 and a.std() > 0 and b.std() > 0:
            corr = float(torch.corrcoef(torch.stack([a, b]))[0, 1])
        rms = float(a.pow(2).mean().sqrt()) if limit else None
        rows.append({
            "row": i,
            "samples_base": int(base[i].numel()),
            "samples_half": int(half[i].numel()),
            "max_abs_diff": diff,
            "corr": corr,
            "rms_base": rms,
        })

    OUT.mkdir(parents=True, exist_ok=True)
    import soundfile as sf

    for name, data in (("mimi_fp32.wav", base), ("mimi_fp16.wav", half)):
        sf.write(OUT / name, torch.cat(data).numpy(), sr)

    corrs = [r["corr"] for r in rows if r["corr"] is not None]
    maxdiff = max(r["max_abs_diff"] for r in rows if r["max_abs_diff"] is not None)
    data = {
        "probe": "check_mimi_fp16",
        "gpu_name": torch.cuda.get_device_name(0),
        "rows": rows,
        "min_corr": min(corrs) if corrs else None,
        "max_abs_diff": maxdiff,
        "sr": sr,
    }
    (OUT / "check_mimi_fp16.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({k: data[k] for k in ("min_corr", "max_abs_diff")}))
    ok = bool(corrs) and min(corrs) >= 0.99
    print("CHECK_MIMI_FP16", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
