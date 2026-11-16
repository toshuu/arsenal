"""GPU memory items at large B: weights, voice state, peak activations/workspace."""

import argparse
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
sys.path.insert(0, str(REPO / "Code" / "probes"))
OUT = REPO / "Code" / "probes" / "out" / "probe_memory.json"


def _mb(tensors) -> float:
    return sum(t.numel() * t.element_size() for t in tensors) / 2**20


def child(b: int, q) -> None:
    try:
        os.chdir(REPO / "Code" / "model")
        import logging

        logging.disable(logging.CRITICAL)
        from pocket_tts import TTSModel
        from batch.batched_stream import BatchedStream
        from batch.fp16 import enable_fp16_backbone
        from batch.fp16_weights import load_fp16_weights
        from bench_batch_server import make_texts

        model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
        enable_fp16_backbone(model, mimi_fp16=True)
        load_fp16_weights(model, REPO / "Code" / "model" / "fp16_weights.pt")
        weights = _mb([p.detach() for p in model.parameters()])
        stream = BatchedStream(model, voice_profile=REPO / "Code" / "probes" / "out" / "voice_4s_cond.pt",
                               max_first_tokens=16, compact=True)
        voice = _mb([v for m in (stream.voice_state or {}).values()
                     for v in m.values() if torch.is_tensor(v)])
        torch.cuda.reset_peak_memory_stats()
        before = torch.cuda.memory_allocated() / 2**20
        texts = make_texts(400)
        stream.stream(texts[:b], max_frames=32)
        torch.cuda.synchronize()
        peak = torch.cuda.max_memory_allocated() / 2**20
        reserved = torch.cuda.max_memory_reserved() / 2**20
        free, total = torch.cuda.mem_get_info()
        known = weights + voice + before
        q.put({"b": b, "max_allocated_mb": peak, "max_reserved_mb": reserved,
               "free_after_mb": free / 2**20, "total_mb": total / 2**20,
               "weights_mb": weights, "voice_state_mb": voice,
               "other_peak_mb": max(0.0, peak - before - voice),
               "top": [
                   {"name": "weights", "mb": weights},
                   {"name": "voice_state", "mb": voice},
                   {"name": "activations_kv_workspace", "mb": max(0.0, peak - before - voice)},
               ]})
    except Exception as exc:  # noqa: BLE001
        q.put({"b": b, "oom": "OutOfMemory" in repr(exc), "error": repr(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bs", default="192,224,256")
    args = parser.parse_args()
    bs = [int(x) for x in args.bs.split(",") if x.strip()]
    ctx = mp.get_context("spawn")
    data = {"per_b": {}, "top": [], "errors": []}
    for b in bs:
        q = ctx.Queue()
        p = ctx.Process(target=child, args=(b, q), daemon=True)
        p.start()
        try:
            res = q.get(timeout=600)
        except Exception as exc:  # noqa: BLE001
            res = {"b": b, "error": f"timeout: {exc}"}
        p.join(timeout=10)
        if "error" in res:
            data["errors"].append(res)
        else:
            data["per_b"][str(b)] = res
            data["top"] = sorted(res["top"], key=lambda x: -x["mb"])[:3] if b == bs[-1] else data["top"]
        print(b, res, flush=True)
    data["decision"] = "ranked; fix cheapest large item"
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
