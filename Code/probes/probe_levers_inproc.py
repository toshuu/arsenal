"""In-process lever comparison.

Run: python Code/probes/probe_levers_inproc.py
Writes: Code/probes/out/probe_levers_inproc.json
"""

import json
import logging
import os
import random
import sys
import time
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
OUT = REPO / "Code" / "probes" / "out" / "probe_levers_inproc.json"
COMBOS = [(v, c) for v in (6.5, 4.0, 3.0, 2.0) for c in (50, 24, 16)]
BATCHES = (96, 128)
SEED = 11
BURSTS = 3


def main() -> int:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model)
    model.temp = 0.3
    sr = model.config.mimi.sample_rate
    spf = int(round(sr / model.mimi.frame_rate))
    texts = make_texts(128)
    streams = {
        cfg: BatchedStream(model, VOICE, voice_seconds=cfg[0], max_first_tokens=cfg[1])
        for cfg in COMBOS
    }
    for stream in streams.values():
        stream.stream(texts[:4], max_frames=4)
    torch.cuda.synchronize()

    rng = random.Random(SEED)
    samples = {cfg: {b: [] for b in BATCHES} for cfg in COMBOS}
    walls = {cfg: {b: [] for b in BATCHES} for cfg in COMBOS}
    audios = {cfg: {b: [] for b in BATCHES} for cfg in COMBOS}
    peaks = {cfg: {b: 0.0 for b in BATCHES} for cfg in COMBOS}

    for rnd in range(BURSTS):
        order = COMBOS[:]
        rng.shuffle(order)
        for cfg in order:
            stream = streams[cfg]
            for b in BATCHES:
                batch_texts = [texts[(rnd * 7 + r) % len(texts)] for r in range(b)]
                frame_times = [[] for _ in range(b)]
                frame_no = [0] * b
                torch.cuda.reset_peak_memory_stats()
                t0 = time.perf_counter()

                def on_chunk(row, chunk, elapsed):
                    frame_times[row].append(time.perf_counter() - t0)
                    frame_no[row] += 1

                audio = stream.stream(batch_texts, on_chunk=on_chunk)
                torch.cuda.synchronize()
                wall = time.perf_counter() - t0
                for r in range(b):
                    ms = first_sound_ms(audio[r], frame_times[r], spf)
                    if ms is not None:
                        samples[cfg][b].append(ms)
                audio_s = sum(a.numel() for a in audio) / sr
                walls[cfg][b].append(wall)
                audios[cfg][b].append(audio_s)
                peaks[cfg][b] = max(
                    peaks[cfg][b], float(torch.cuda.max_memory_allocated() / 1e6)
                )

    rows = []
    for cfg in COMBOS:
        for b in BATCHES:
            s = samples[cfg][b]
            w = pct(walls[cfg][b], 50)
            a = pct(audios[cfg][b], 50)
            rows.append(
                {
                    "voice_seconds": cfg[0],
                    "first_tokens": cfg[1],
                    "batch": b,
                    "p50_ms": round(pct(s, 50), 2) if s else None,
                    "p95_ms": round(pct(s, 95), 2) if s else None,
                    "under_350": sum(1 for x in s if x <= 350),
                    "samples": len(s),
                    "rtf": round(w / a, 4) if a else None,
                    "vram_mb": round(peaks[cfg][b], 1),
                }
            )
    agg = {
        "probe": "probe_levers_inproc",
        "gpu_name": torch.cuda.get_device_name(0),
        "seed": SEED,
        "bursts": BURSTS,
        "results": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(agg, indent=2) + "\n")
    print("LEVERS_INPROC_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
