"""Measure first-frame and batch-tail for three call text policies."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
OUT = ROOT / "Code" / "probes" / "out" / "natural_stream"
LONG = (
    "Life doesn't always go the way we plan, but sometimes the unexpected "
    "moments turn out to be the most beautiful ones. Since there are many "
    "people in this planet which really wants to do good things for you, so "
    "always enjoy and rejoice this life. Because you never know what "
    "wonderful things are waiting for you to discover."
)
SHORT = "Hello, can you hear me now?"

MODES = {
    "legacy": {
        "max_first_tokens": 16,
        "max_allowed_frames": 192,
        "max_tokens": 50,
        "max_frames": 192,
    },
    "sentence": {
        "max_first_tokens": None,
        "max_allowed_frames": 224,
        "max_tokens": 50,
        "max_frames": 224,
    },
    "utterance": {
        "max_first_tokens": None,
        "max_allowed_frames": 512,
        "max_tokens": 512,
        "max_frames": 256,
    },
}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    data = sorted(values)
    index = min(len(data) - 1, int(len(data) * fraction))
    return round(float(data[index]), 2)


def summarize(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": round(float(max(values)), 2) if values else None,
        "min": round(float(min(values)), 2) if values else None,
    }


def write_wav(path: Path, samples, rate: int = 24000) -> None:
    data = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2").tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


def gap_stats(audio, rate: int = 24000, thr: float = 0.01, min_ms: int = 150) -> dict:
    data = np.asarray(audio, dtype="float32").reshape(-1)
    gaps: list[float] = []
    index = 0
    total = len(data)
    while index < total:
        if abs(float(data[index])) < thr:
            end = index
            while end < total and abs(float(data[end])) < thr:
                end += 1
            ms = (end - index) * 1000.0 / rate
            if ms >= min_ms:
                gaps.append(round(ms, 1))
            index = end
        else:
            index += 1
    return {
        "count": len(gaps),
        "max_ms": max(gaps) if gaps else 0.0,
        "total_ms": round(sum(gaps), 1),
    }


def texts_for(batch: int, mix: str) -> list[str]:
    if mix == "same":
        return [LONG] * batch
    return [SHORT if index % 2 == 0 else LONG for index in range(batch)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(MODES), required=True)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--mix", choices=("same", "mixed"), default="same")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out_path = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
    out_dir = out_path.parent

    sys.path.insert(0, str(ROOT / "Code"))
    os.chdir(ROOT / "Code" / "model")
    logging.disable(logging.CRITICAL)

    import torch
    from pocket_tts import TTSModel

    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from batch.fp16_weights import load_fp16_weights

    config = MODES[args.mode]
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=True)
    weights = Path("fp16_weights.pt")
    if weights.exists():
        load_fp16_weights(model, weights)

    stream = BatchedStream(
        model,
        voice=str(REF),
        voice_seconds=4.0,
        max_first_tokens=config["max_first_tokens"],
        max_allowed_frames=config["max_allowed_frames"],
        max_tokens=config["max_tokens"],
        compact=True,
        decode_group=1,
    )
    texts = texts_for(args.batch, args.mix)
    runs = []
    all_first: list[float] = []
    warm_first: list[float] = []
    walls: list[float] = []
    warm_walls: list[float] = []
    last_values: list[float] = []
    warm_last: list[float] = []
    cold_first = {}
    cold_wall = None
    gap_summary = {"count": 0, "max_ms": 0.0, "total_ms": 0.0}

    for rep in range(args.reps):
        first: dict[int, float] = {}
        last: dict[int, float] = {}

        def on_chunk(row: int, frame, elapsed: float) -> None:
            now = time.perf_counter()
            first.setdefault(row, now)
            last[row] = now

        torch.cuda.synchronize()
        if rep == 0:
            torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        audio = stream.stream(
            texts,
            max_frames=config["max_frames"],
            on_chunk=on_chunk,
        )
        torch.cuda.synchronize()
        wall_ms = (time.perf_counter() - start) * 1000.0
        first_ms = [(first[row] - start) * 1000.0 for row in range(len(texts)) if row in first]
        last_ms = [(last[row] - start) * 1000.0 for row in range(len(texts)) if row in last]
        all_first.extend(first_ms)
        walls.append(round(wall_ms, 2))
        last_values = last_ms

        row_gaps = []
        for index, item in enumerate(audio):
            samples = item.detach().float().cpu().numpy()
            stats = gap_stats(samples)
            row_gaps.append(stats)
            gap_summary["count"] += stats["count"]
            gap_summary["max_ms"] = max(gap_summary["max_ms"], stats["max_ms"])
            gap_summary["total_ms"] = round(gap_summary["total_ms"] + stats["total_ms"], 1)
            if rep == 0 and index < 5:
                path = OUT / f"{args.mode}_{args.batch}_{args.mix}_{index}.wav"
                write_wav(path, samples)

        runs.append(
            {
                "rep": rep,
                "wall_ms": round(wall_ms, 2),
                "first_ms": summarize(first_ms),
                "last_ms": summarize(last_ms),
                "row_gaps": row_gaps,
            }
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": args.mode,
                    "batch": args.batch,
                    "mix": args.mix,
                    "rep": rep,
                    "first_p95": runs[-1]["first_ms"]["p95"],
                    "wall_ms": runs[-1]["wall_ms"],
                }
            ),
            flush=True,
        )

    summary = {
        "mode": args.mode,
        "batch": args.batch,
        "mix": args.mix,
        "reps": args.reps,
        "config": config,
        "first_frame_ms": summarize(warm_first if warm_first else all_first),
        "cold_first_frame_ms": cold_first,
        "batch_wall_ms": summarize(warm_walls if warm_walls else walls),
        "cold_batch_wall_ms": cold_wall,
        "last_frame_ms": summarize(warm_last if warm_last else last_values),
        "gaps": gap_summary,
        "vram_peak_mb": round(torch.cuda.max_memory_allocated() / (1024 ** 2), 1),
        "runs": runs,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"ok": True, "out": str(out_path)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
