"""TTFA stage probe with a separate load generator (E0 of IDEA-0004).

The server child owns the model. The parent is the load generator. It sends
one burst, waits, and sends the next burst. Absolute perf_counter values from
both processes use the system-wide Linux monotonic clock.

Run from the repository root:
  python Code/probes/probe_ttfa_stages.py --bs 128,160 --bursts 5 --rounds 2

Writes Code/probes/out/probe_ttfa_stages.json.
"""

import argparse
import json
import multiprocessing as mp
import os
import subprocess
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REF = REPO / "Code" / "probes" / "ref" / "voice.wav"
PROFILE = REPO / "Code" / "probes" / "out" / "voice_4s_cond.pt"
OUT = REPO / "Code" / "probes" / "out" / "probe_ttfa_stages.json"

SUBJECTS = [
    "The old sailor", "A young engineer", "The quiet librarian",
    "A careful painter", "The tired farmer", "A curious student",
    "The local baker", "A friendly driver",
]
VERBS = [
    "found", "opened", "carried", "noticed",
    "cleaned", "painted", "measured", "packed",
]
OBJECTS = [
    "a brass key", "an old map", "a small lantern", "a folded letter",
    "a wooden box", "a silver coin", "a blue notebook", "a broken clock",
]
PLACES = [
    "harbor", "station", "garden", "library",
    "workshop", "market", "courtyard", "lighthouse",
]


def make_texts(count):
    texts = []
    for index in range(count):
        subject = SUBJECTS[index % len(SUBJECTS)]
        verb = VERBS[(index // len(SUBJECTS)) % len(VERBS)]
        obj = OBJECTS[(index // 4) % len(OBJECTS)]
        place = PLACES[(index * 3) % len(PLACES)]
        texts.append(
            f"{subject} {verb} {obj} while the wind moved slowly near the "
            f"{place}, and waited for the morning train."
        )
    return texts


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = (q / 100.0) * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def summarize_ms(values):
    return {
        "p50": round(percentile(values, 50), 3) if values else None,
        "p95": round(percentile(values, 95), 3) if values else None,
        "mean": round(sum(values) / len(values), 3) if values else None,
        "max": round(max(values), 3) if values else None,
    }


class ResourceSampler:
    def __init__(self):
        self.samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def _cpu():
        try:
            with open("/proc/stat") as handle:
                parts = handle.readline().split()[1:]
            vals = [int(x) for x in parts]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            return idle, sum(vals)
        except OSError:
            return None

    def _run(self):
        prev = self._cpu()
        while not self._stop.wait(0.2):
            gpu = None
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=2,
                )
                if out.returncode == 0 and out.stdout.strip():
                    gpu = float(out.stdout.strip().splitlines()[0])
            except (OSError, ValueError, subprocess.SubprocessError):
                gpu = None
            cur = self._cpu()
            cpu = None
            if prev is not None and cur is not None:
                d_idle = cur[0] - prev[0]
                d_total = cur[1] - prev[1]
                if d_total > 0:
                    cpu = 100.0 * (1.0 - d_idle / d_total)
            prev = cur
            self.samples.append({"gpu": gpu, "cpu": cpu})

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)


def server(cmd_q, res_q, profile_path, voice_path, bs, frames, fp16_mimi, decode_group, overlap):
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    os.chdir(REPO / "Code" / "model")
    import logging

    import torch

    logging.disable(logging.CRITICAL)
    import sys

    sys.path.insert(0, str(REPO / "Code"))
    from pocket_tts import TTSModel

    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone

    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=fp16_mimi)
    model.temp = 0.3
    profile = Path(profile_path)
    if not profile.exists():
        base = BatchedStream(model, voice=voice_path, voice_seconds=4.0, max_first_tokens=16)
        profile.parent.mkdir(parents=True, exist_ok=True)
        base.save_voice_profile(profile, conditioned=True)
    stream = BatchedStream(model, voice_profile=profile, max_first_tokens=16, compact=True, decode_group=decode_group, overlap_decode=overlap)
    sr = model.config.mimi.sample_rate
    texts = make_texts(400)
    for b in bs:
        stream.stream(texts[: min(8, b)], max_frames=8)
    torch.cuda.synchronize()
    res_q.put(("ready", torch.cuda.get_device_name(0)))
    while True:
        msg = cmd_q.get()
        if msg[0] == "stop":
            return
        _, round_id, burst_id, b, t_send = msg
        batch_texts = [texts[(burst_id * 7 + row) % len(texts)] for row in range(b)]
        batch_stages = {}
        first_emit = {}

        def on_stage(row, name, t):
            if row < 0:
                batch_stages[name] = t
            elif name == "first_emit" and row not in first_emit:
                first_emit[row] = t

        t_recv = time.perf_counter()
        try:
            audio = stream.stream(
                batch_texts, on_stage=on_stage, max_frames=frames or None
            )
            torch.cuda.synchronize()
        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
            torch.cuda.empty_cache()
            res_q.put({"round": round_id, "burst": burst_id, "b": b,
                       "t_send": t_send, "t_recv": t_recv, "error": repr(exc)})
            continue
        samples = sum(int(a.numel()) for a in audio)
        res_q.put({
            "round": round_id,
            "burst": burst_id,
            "b": b,
            "t_send": t_send,
            "t_recv": t_recv,
            "t_end": time.perf_counter(),
            "stages": batch_stages,
            "first_emit": first_emit,
            "samples": samples,
            "sr": sr,
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bs", default="128,160")
    parser.add_argument("--bursts", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--fp16-mimi", action="store_true")
    parser.add_argument("--decode-group", type=int, default=1)
    parser.add_argument("--overlap", action="store_true")
    parser.add_argument("--profile", default=str(PROFILE))
    parser.add_argument("--voice", default=str(REF))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--threshold-ms", type=float, default=350.0)
    args = parser.parse_args()

    bs = [int(x) for x in args.bs.split(",") if x.strip()]
    ctx = mp.get_context("spawn")
    cmd_q = ctx.Queue()
    res_q = ctx.Queue()
    proc = ctx.Process(target=server, args=(cmd_q, res_q, args.profile, args.voice, bs, args.frames, args.fp16_mimi, args.decode_group, args.overlap), daemon=True)
    proc.start()
    ready = res_q.get(timeout=300)
    if ready[0] != "ready":
        raise RuntimeError(f"server failed: {ready}")
    gpu_name = ready[1]
    print("server ready on", gpu_name, flush=True)

    sampler = ResourceSampler()
    sampler.start()
    collected = []
    errors = []
    try:
        for round_id in range(args.rounds):
            for b in bs:
                for burst_id in range(args.bursts):
                    t_send = time.perf_counter()
                    cmd_q.put(("burst", round_id, burst_id, b, t_send))
                    result = res_q.get(timeout=900)
                    if result.get("error"):
                        print(f"round={round_id} b={b} burst={burst_id} ERROR {result['error']}", flush=True)
                        errors.append({"b": b, "burst": burst_id, "error": result["error"]})
                        continue
                    collected.append(result)
                    ttfa = [(t - t_send) * 1000.0 for t in result["first_emit"].values()]
                    print(
                        f"round={round_id} b={b} burst={burst_id} "
                        f"rows={len(ttfa)} ttfa_p95={round(percentile(ttfa, 95), 2)} ms",
                        flush=True,
                    )
    finally:
        cmd_q.put(("stop",))
        sampler.stop()
        proc.join(timeout=30)
        if proc.is_alive():
            proc.terminate()

    stages = {}
    for b in bs:
        rows = [r for r in collected if r["b"] == b]
        keys = ["queue_ms", "prep_ms", "state_ms", "cond_ms", "flow0_ms",
                "mimi0_ms", "emit_ms", "ttfa_ms", "compute_ms", "gap_ms"]
        acc = {k: [] for k in keys}
        for result in rows:
            s = result["stages"]
            queue = (s.get("stream_start", result["t_recv"]) - result["t_send"]) * 1000.0
            prep = (s.get("prep_done", 0.0) - s.get("prep_start", 0.0)) * 1000.0
            state = (s.get("state_done", 0.0) - s.get("prep_done", 0.0)) * 1000.0
            cond = (s.get("cond_done", 0.0) - s.get("state_done", 0.0)) * 1000.0
            flow0 = (s.get("flow0_done", 0.0) - s.get("cond_done", 0.0)) * 1000.0
            mimi0 = (s.get("mimi0_done", 0.0) - s.get("flow0_done", 0.0)) * 1000.0
            for t in result["first_emit"].values():
                emit = (t - s.get("mimi0_done", t)) * 1000.0
                ttfa = (t - result["t_send"]) * 1000.0
                compute = prep + state + cond + flow0 + mimi0 + emit
                acc["queue_ms"].append(queue)
                acc["prep_ms"].append(prep)
                acc["state_ms"].append(state)
                acc["cond_ms"].append(cond)
                acc["flow0_ms"].append(flow0)
                acc["mimi0_ms"].append(mimi0)
                acc["emit_ms"].append(emit)
                acc["ttfa_ms"].append(ttfa)
                acc["compute_ms"].append(compute)
                acc["gap_ms"].append(ttfa - compute - queue)
        summary = {k: summarize_ms(acc[k]) for k in keys}
        under = sum(1 for x in acc["ttfa_ms"] if x <= args.threshold_ms)
        total = len(acc["ttfa_ms"])
        summary["under"] = under
        summary["total"] = total
        summary["under_pct"] = round(100.0 * under / total, 3) if total else None
        steady = []
        for result in rows:
            n_frames = result["samples"] / result["sr"] / 0.08 / result["b"]
            if n_frames > 1:
                burst_ttfa = percentile(
                    [(t - result["t_send"]) * 1000.0 for t in result["first_emit"].values()], 50
                )
                steady.append(((result["t_end"] - result["t_recv"]) * 1000.0 - burst_ttfa) / (n_frames - 1))
        summary["steady_ms"] = summarize_ms(steady)
        stages[str(b)] = summary

    gpu_vals = [s["gpu"] for s in sampler.samples if s["gpu"] is not None]
    cpu_vals = [s["cpu"] for s in sampler.samples if s["cpu"] is not None]
    data = {
        "probe": "probe_ttfa_stages",
        "mode": "separate-process load generator, one server child",
        "gpu_name": gpu_name,
        "bs": bs,
        "bursts": args.bursts,
        "rounds": args.rounds,
        "threshold_ms": args.threshold_ms,
        "frames": args.frames,
        "fp16_mimi": args.fp16_mimi,
        "decode_group": args.decode_group,
        "errors": errors,
        "stages": stages,
        "util": {
            "gpu_mean": round(sum(gpu_vals) / len(gpu_vals), 2) if gpu_vals else None,
            "gpu_max": max(gpu_vals) if gpu_vals else None,
            "cpu_mean": round(sum(cpu_vals) / len(cpu_vals), 2) if cpu_vals else None,
            "cpu_max": max(cpu_vals) if cpu_vals else None,
            "samples": len(sampler.samples),
        },
        "done": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({b: stages[b]["ttfa_ms"] for b in stages}))
    print("TTFA_STAGES_DONE")


if __name__ == "__main__":
    main()
