"""Quality/parity check for FP16 batched path.

Run: python Code/probes/check_batch_fp16.py
Writes: Code/probes/out/check_batch_fp16.json
Prints: CHECK_BATCH_FP16 PASS or FAIL
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
from bench_batch_server import make_texts, pct, first_sound_ms  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"


def run_one(model, texts, b, frames=32, bursts=3, temp=0.3):
    model.temp = temp
    stream = BatchedStream(model, VOICE)
    spf = int(round(model.config.mimi.sample_rate / model.config.mimi.frame_rate))
    stream.stream(texts[:4], max_frames=8)
    torch.cuda.synchronize()
    all_first = []
    for burst in range(bursts):
        batch_texts = [texts[(burst * 7 + r) % len(texts)] for r in range(b)]
        ft = [[] for _ in range(b)]
        fn = [0] * b
        t0 = __import__("time").perf_counter()

        def cb(row, chunk, elapsed):
            if row == 0 and fn[row] < 5:
                torch.cuda.synchronize()
            ft[row].append(__import__("time").perf_counter() - t0)
            fn[row] += 1

        torch.cuda.reset_peak_memory_stats()
        audio = stream.stream(batch_texts, on_chunk=cb)
        torch.cuda.synchronize()
        for r in range(b):
            fs = first_sound_ms(audio[r], ft[r], spf)
            if fs is not None:
                all_first.append(fs)
    mb = float(torch.cuda.max_memory_allocated() / 1e6)
    return {
        "batch": b,
        "p50_ms": round(pct(all_first, 50), 2),
        "p95_ms": round(pct(all_first, 95), 2),
        "max_ms": round(max(all_first), 2),
        "under_360": sum(1 for x in all_first if x <= 360),
        "samples": len(all_first),
        "vram_mb": round(mb, 1),
    }


def main():
    texts = make_texts(96)
    # FP32 reference
    m32 = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    m32.temp = 0.0
    bs32 = BatchedStream(m32, VOICE)
    ref = bs32.stream([texts[0]], max_frames=32)[0].cpu()
    del m32, bs32
    torch.cuda.empty_cache()

    # FP16
    m16 = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(m16)
    m16.temp = 0.0
    bs16 = BatchedStream(m16, VOICE)
    a16 = bs16.stream([texts[0]], max_frames=32)[0].cpu()
    a16b = bs16.stream(texts[:32], max_frames=32)[0].cpu()
    diff = float((ref - a16).abs().max())
    corr = float(torch.corrcoef(torch.stack([ref, a16]))[0, 1]) if ref.std() > 0 and a16.std() > 0 else None
    diff_b32 = float((a16 - a16b).abs().max())
    corr_b32 = float(torch.corrcoef(torch.stack([a16, a16b]))[0, 1]) if a16.std() > 0 and a16b.std() > 0 else None

    # TTFA checks
    t32 = run_one(m16, texts, 32, bursts=2, temp=0.3)
    t64 = run_one(m16, texts, 64, bursts=3, temp=0.3)
    t80 = run_one(m16, texts, 80, bursts=3, temp=0.3)

    out = {
        "parity_vs_fp32_b1": {"max_abs_diff": diff, "corr": corr},
        "parity_fp16_b1_vs_b32": {"max_abs_diff": diff_b32, "corr": corr_b32},
        "ttfa": [t32, t64, t80],
        "finite": bool(torch.isfinite(a16).all()),
    }
    ok = (
        out["finite"]
        and corr is not None and corr > 0.99
        and diff < 0.1
        and corr_b32 is not None and corr_b32 > 0.94
        and t64["p95_ms"] < 360
    )
    out["warnings"] = []
    if corr_b32 is not None and corr_b32 <= 0.99:
        out["warnings"].append(f"fp16 b1 vs b32 corr {corr_b32:.4f} < 0.99 (batch-size numeric drift)")
    if t80["p95_ms"] >= 360:
        out["warnings"].append(f"b80 p95 {t80['p95_ms']} >= 360")
    out["result"] = "PASS" if ok else "FAIL"
    path = REPO / "Code" / "probes" / "out" / "check_batch_fp16.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print("CHECK_BATCH_FP16 PASS" if ok else "CHECK_BATCH_FP16 FAIL")
    print(json.dumps(out, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
