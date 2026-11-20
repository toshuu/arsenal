"""Burst concurrency probe for pocket-tts on CPU only.

Each request runs in one process with one model copy. The CPU device is
forced. GPU use is disabled in every worker. All requests start at the
same time. The probe reports time to first audible audio (TTFA) and the
number of requests that finish without an error.

Usage:
  python Code/probes/bench_burst_cpu.py --counts 1,2,4,8 --threads 1

Writes Code/probes/out/bench_burst_cpu.json.
"""

import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO / "Code" / "model"
REF = REPO / "Code" / "probes" / "ref" / "voice.wav"
OUT = REPO / "Code" / "probes" / "out" / "bench_burst_cpu.json"
TEXT = "Hello, this is a short test sentence."


def worker(threads, start_evt, q, text):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.chdir(MODEL_DIR)
    import copy
    import logging

    import torch

    logging.disable(logging.CRITICAL)
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    sys_path = "/kaggle/working/pocket-tts"
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    from pocket_tts import TTSModel

    try:
        model = TTSModel.load_model(config="config.yaml").to("cpu").eval()
        state = model.get_state_for_audio_prompt(str(REF))
        for _chunk in model.generate_audio_stream(copy.deepcopy(state), text):
            pass
        q.put(("ready", os.getpid()))
        start_evt.wait()
        t0 = time.perf_counter()
        first_chunk = None
        first_sound = None
        chunks = 0
        duration = 0.0
        for chunk in model.generate_audio_stream(copy.deepcopy(state), text):
            now = time.perf_counter() - t0
            if first_chunk is None:
                first_chunk = now
            if first_sound is None and float(chunk.abs().max()) > 0.01:
                first_sound = now
            chunks += 1
            duration += chunk.shape[0] / model.sample_rate
        q.put(("done", os.getpid(), first_chunk, first_sound, chunks, duration))
    except Exception as exc:  # noqa: BLE001
        q.put(("error", os.getpid(), repr(exc)))


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((p / 100.0) * len(ordered) + 0.5)) - 1))
    return ordered[idx]


def run_burst(ctx, n, threads, text, timeout=600):
    evt = ctx.Event()
    q = ctx.Queue()
    load_start = time.perf_counter()
    procs = [ctx.Process(target=worker, args=(threads, evt, q, text)) for _ in range(n)]
    for p in procs:
        p.start()
    ready = []
    errors = []
    for _ in range(n):
        msg = q.get(timeout=timeout)
        if msg[0] == "ready":
            ready.append(msg)
        else:
            errors.append(msg)
    if len(ready) != n:
        evt.set()
        for p in procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
        return {
            "n": n,
            "threads": threads,
            "ready": len(ready),
            "errors": [m[-1] for m in errors],
            "load_seconds": round(time.perf_counter() - load_start, 3),
        }
    load_seconds = time.perf_counter() - load_start
    wall_start = time.perf_counter()
    evt.set()
    done = []
    for _ in range(n):
        msg = q.get(timeout=timeout)
        if msg[0] == "done":
            done.append(msg)
        else:
            errors.append(msg)
    wall_seconds = time.perf_counter() - wall_start
    for p in procs:
        p.join(timeout=30)
        if p.is_alive():
            p.terminate()

    first_chunks = [m[2] for m in done if m[2] is not None]
    first_sounds = [m[3] for m in done if m[3] is not None]
    return {
        "n": n,
        "threads": threads,
        "ready": len(ready),
        "done": len(done),
        "errors": [m[-1] for m in errors],
        "load_seconds": round(load_seconds, 3),
        "wall_seconds": round(wall_seconds, 3),
        "first_chunk_ms": {
            "p50": round(percentile(first_chunks, 50) * 1000, 2) if first_chunks else None,
            "p95": round(percentile(first_chunks, 95) * 1000, 2) if first_chunks else None,
            "p99": round(percentile(first_chunks, 99) * 1000, 2) if first_chunks else None,
        },
        "first_sound_ms": {
            "p50": round(percentile(first_sounds, 50) * 1000, 2) if first_sounds else None,
            "p95": round(percentile(first_sounds, 95) * 1000, 2) if first_sounds else None,
            "p99": round(percentile(first_sounds, 99) * 1000, 2) if first_sounds else None,
        },
        "samples_first_sound_ms": [round(x * 1000, 2) for x in first_sounds],
        "samples_first_chunk_ms": [round(x * 1000, 2) for x in first_chunks],
        "audio_seconds": round(sum(m[5] for m in done) / len(done), 3) if done else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--counts", default="1,2,4,8")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--text", default=TEXT)
    parser.add_argument("--threshold-ms", type=float, default=1000.0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    counts = [int(x) for x in args.counts.split(",") if x.strip()]
    ctx = mp.get_context("spawn")
    runs = []
    for n in counts:
        print(f"burst n={n} cpu threads={args.threads} repeats={args.repeats}", flush=True)
        bursts = [run_burst(ctx, n, args.threads, args.text) for _ in range(args.repeats)]
        sounds = [x for b in bursts for x in b.get("samples_first_sound_ms", [])]
        chunks = [x for b in bursts for x in b.get("samples_first_chunk_ms", [])]
        total = sum(b.get("done", 0) for b in bursts)
        errors = [e for b in bursts for e in b.get("errors", [])]
        within = sum(1 for x in sounds if x <= args.threshold_ms)
        result = {
            "n": n,
            "threads": args.threads,
            "repeats": args.repeats,
            "requests": total,
            "errors": errors,
            "load_seconds": [b.get("load_seconds") for b in bursts],
            "wall_seconds": [b.get("wall_seconds") for b in bursts],
            "first_chunk_ms": {
                "p50": round(percentile(chunks, 50), 2) if chunks else None,
                "p95": round(percentile(chunks, 95), 2) if chunks else None,
                "p99": round(percentile(chunks, 99), 2) if chunks else None,
            },
            "first_sound_ms": {
                "p50": round(percentile(sounds, 50), 2) if sounds else None,
                "p95": round(percentile(sounds, 95), 2) if sounds else None,
                "p99": round(percentile(sounds, 99), 2) if sounds else None,
            },
            "within_threshold": within,
            "within_threshold_pct": round(100.0 * within / len(sounds), 1) if sounds else None,
            "samples_first_sound_ms": sounds,
            "bursts": bursts,
        }
        runs.append(result)
        fs = result["first_sound_ms"]
        print(
            f"  requests={total} errors={len(errors)} "
            f"ttfa p50={fs['p50']} p95={fs['p95']} p99={fs['p99']} ms "
            f"smooth={within}/{len(sounds)} <= {int(args.threshold_ms)}ms",
            flush=True,
        )

    passing = [
        r["n"]
        for r in runs
        if not r.get("errors")
        and r.get("requests") == r["n"] * r["repeats"]
        and r.get("first_sound_ms", {}).get("p95") is not None
        and r["first_sound_ms"]["p95"] <= args.threshold_ms
    ]
    data = {
        "probe": "bench_burst_cpu",
        "device": "cpu",
        "mode": "process-per-request, one model copy per request, no batching",
        "threads_per_request": args.threads,
        "threshold_ms": args.threshold_ms,
        "metric": "first non-silent audio chunk (TTFA), p95 across concurrent requests",
        "runs": runs,
        "max_n_under_threshold": max(passing) if passing else None,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n")
    print("max_n_under_threshold", data["max_n_under_threshold"])
    print("wrote", out)


if __name__ == "__main__":
    main()
