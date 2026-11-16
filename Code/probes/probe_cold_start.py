"""Cold-start probe: boot, single-request and first-burst cost on fresh processes."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "Code" / "probes" / "out"
VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"


def _stats(values: list[float]) -> dict:
    if not values:
        return {"p50": None, "p95": None, "max": None, "n": 0}
    ordered = sorted(values)
    def q(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1))))]
    return {"p50": q(50), "p95": q(95), "max": ordered[-1], "n": len(ordered)}


def child(mode: str, bs: list[int], one_b: int, fp16_weights: bool, prewarm_b: int, prefetch: bool, q) -> None:
    t_start = time.perf_counter()
    if prefetch:
        import threading
        def _read():
            (REPO / "Code" / "model" / "model.safetensors").read_bytes()
        threading.Thread(target=_read, daemon=True).start()
    phases: dict[str, float] = {}
    try:
        t = time.perf_counter()
        import torch
        phases["import_torch_ms"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        torch.cuda.init()
        torch.cuda.synchronize()
        phases["cuda_init_ms"] = (time.perf_counter() - t) * 1000

        sys.path.insert(0, str(REPO / "Code"))
        os.chdir(REPO / "Code" / "model")
        import logging

        logging.disable(logging.CRITICAL)
        from pocket_tts import TTSModel

        t = time.perf_counter()
        model = TTSModel.load_model(config="config.yaml")
        phases["weight_read_ms"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        model = model.to("cuda").eval()
        torch.cuda.synchronize()
        phases["to_gpu_ms"] = (time.perf_counter() - t) * 1000

        from batch.batched_stream import BatchedStream
        from batch.fp16 import enable_fp16_backbone
        sys.path.insert(0, str(REPO / "Code" / "probes"))
        from bench_batch_server import make_texts

        t = time.perf_counter()
        enable_fp16_backbone(model, mimi_fp16=True)
        if fp16_weights:
            from batch.fp16_weights import load_fp16_weights
            load_fp16_weights(model, REPO / "Code" / "model" / "fp16_weights.pt")
        torch.cuda.synchronize()
        phases["fp16_ms"] = (time.perf_counter() - t) * 1000
        model.temp = 0.0
        stream = None
        texts = None
        prewarm_ms = 0.0
        if mode != "boot" or prewarm_b:
            from batch.boot import maybe_prewarm
            tp = time.perf_counter()
            stream = BatchedStream(model, voice=str(VOICE), voice_seconds=4.0,
                                   max_first_tokens=16, compact=True)
            texts = make_texts(400)
            phases["stream_ms"] = (time.perf_counter() - tp) * 1000
            if prewarm_b:
                os.environ["ARSENAL_PREWARM_B"] = str(prewarm_b)
                prewarm_ms = maybe_prewarm(stream, texts)
        phases["prewarm_ms"] = prewarm_ms
        phases["ready_ms"] = (time.perf_counter() - t_start) * 1000
        phases["ready_wall"] = time.perf_counter()

        free_ready, total = torch.cuda.mem_get_info()
        result = {
            "boot": {"phases_ms": phases, "total_ms": phases["ready_ms"],
                     "free_ready_mb": free_ready / 2**20, "total_mb": total / 2**20},
            "device": torch.cuda.get_device_name(0),
        }
        if mode == "boot":
            q.put(result)
            return

        if stream is None:
            stream = BatchedStream(model, voice=str(VOICE), voice_seconds=4.0,
                                   max_first_tokens=16, compact=True)
            texts = make_texts(400)
        result["prewarm_ms"] = prewarm_ms

        def run_burst(batch_texts, t_send):
            first: dict[int, float] = {}
            stages: dict[str, float] = {}

            def on_stage(row, name, t):
                if row < 0:
                    stages[name] = t
                elif name == "first_emit":
                    if row not in first:
                        first[row] = t
                    if row == 0:
                        stages["first_emit"] = t

            stream.stream(batch_texts, on_stage=on_stage)
            ttfa = [(t - t_send) * 1000 for t in first.values()]
            return ttfa, stages

        if mode == "single":
            t_send = time.perf_counter()
            ttfa, stages = run_burst([texts[0]], t_send)
            warm_t, _ = run_burst([texts[0]], time.perf_counter())
            base = stages.get("stream_start", t_send)
            result["single"] = {
                "ttfa_ms": ttfa[0] if ttfa else None,
                "warm_ttfa_ms": warm_t[0] if warm_t else None,
                "stages_ms": {
                    "prep": (stages.get("prep_done", 0) - base) * 1000,
                    "state": (stages.get("state_done", 0) - base) * 1000,
                    "cond": (stages.get("cond_done", 0) - base) * 1000,
                    "flow0": (stages.get("flow0_done", 0) - base) * 1000,
                    "mimi0": (stages.get("mimi0_done", 0) - base) * 1000,
                },
            }
        else:
            result["burst"] = {}
            for b in ([one_b] if one_b else bs):
                cold, cold_stages = run_burst(texts[:b], time.perf_counter())
                warm, _ = run_burst(texts[:b], time.perf_counter())
                base = cold_stages.get("stream_start", 0)
                result["burst"][str(b)] = {
                    "cold": _stats(cold),
                    "warm": _stats(warm),
                    "breakdown_ms": {
                        "prep": (cold_stages.get("prep_done", 0) - base) * 1000,
                        "state": (cold_stages.get("state_done", 0) - base) * 1000,
                        "cond": (cold_stages.get("cond_done", 0) - base) * 1000,
                        "flow0": (cold_stages.get("flow0_done", 0) - base) * 1000,
                        "mimi0": (cold_stages.get("mimi0_done", 0) - base) * 1000,
                        "emit0": (cold_stages.get("first_emit", 0) - base) * 1000,
                    },
                }
                free, _ = torch.cuda.mem_get_info()
                result["burst"][str(b)]["free_after_mb"] = free / 2**20
                result["burst"][str(b)]["max_allocated_mb"] = torch.cuda.max_memory_allocated() / 2**20
                torch.cuda.empty_cache()
        q.put(result)
    except Exception as exc:  # noqa: BLE001
        import traceback
        q.put({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(),
               "mode": mode})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bs", default="96,128,160,176,192")
    parser.add_argument("--fp16-weights", action="store_true")
    parser.add_argument("--prewarm", type=int, default=0)
    parser.add_argument("--prefetch", action="store_true")
    parser.add_argument("--out", default=str(OUT / "probe_cold_start.json"))
    args = parser.parse_args()
    bs = [int(x) for x in args.bs.split(",") if x.strip()]
    ctx = mp.get_context("spawn")
    data: dict = {"burst": {}, "errors": []}

    for mode, scenarios in (("boot", [0]), ("single", [0]), ("burst", bs)):
        for b in scenarios:
            q = ctx.Queue()
            t0 = time.perf_counter()
            proc = ctx.Process(target=child, args=(mode, bs, b, args.fp16_weights, args.prewarm, args.prefetch, q), daemon=True)
            proc.start()
            try:
                res = q.get(timeout=900)
            except Exception as exc:  # noqa: BLE001
                res = {"error": f"timeout: {exc}"}
            proc.join(timeout=10)
            wall = (time.perf_counter() - t0) * 1000
            if "error" in res:
                data["errors"].append({"mode": mode, "b": b, **res})
                continue
            res["spawn_to_result_ms"] = wall
            if mode == "boot":
                data["boot"] = res
            elif mode == "single":
                data["single"] = res
            else:
                data["burst"].update(res["burst"])
                data.setdefault("bootstrap", []).append(res.get("boot", {}))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({k: data.get(k) is not None for k in ("boot", "single", "burst")}))
    print("COLD_START_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
