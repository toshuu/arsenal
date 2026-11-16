"""Per-component steady-frame profile: flow, Mimi, other."""

import json
import logging
import os
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
from batch.fp16_weights import load_fp16_weights  # noqa: E402
from bench_batch_server import make_texts  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
PROFILE = REPO / "Code" / "probes" / "out" / "voice_4s_cond.pt"
WEIGHTS = REPO / "Code" / "model" / "fp16_weights.pt"
OUT = REPO / "Code" / "probes" / "out" / "probe_components.json"


def main() -> int:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=True)
    load_fp16_weights(model, WEIGHTS)
    model.temp = 0.3
    if not PROFILE.exists():
        base = BatchedStream(model, voice=str(VOICE), voice_seconds=4.0, max_first_tokens=16)
        base.save_voice_profile(PROFILE, conditioned=True)
    texts = make_texts(400)
    data = {"gpu": torch.cuda.get_device_name(0), "bs": {}}
    for b in (160, 192, 224):
        try:
            stream = BatchedStream(model, voice_profile=PROFILE, max_first_tokens=16,
                                   compact=True, profile_steps=True)
            stream.stream(texts[:b], max_frames=None)
            t = time.perf_counter()
            stream.stream(texts[:b], max_frames=None)
            torch.cuda.synchronize()
            wall = (time.perf_counter() - t) * 1000.0
            prof = stream.last_profile
            steps = prof["steps"] or 1
            flow = prof["flow_ms"] / steps
            mimi = prof["mimi_ms"] / steps
            emit = prof.get("emit_ms", 0.0) / steps
            loop = prof.get("loop_ms", 0.0) / steps
            steady = wall / steps
            data["bs"][str(b)] = {
                "steps": steps,
                "steady_ms": steady,
                "flow_ms": flow,
                "mimi_ms": mimi,
                "emit_ms": emit,
                "loop_ms": loop,
                "other_ms": steady - flow - mimi - emit,
                "peak_vram_mb": torch.cuda.max_memory_allocated() / 2**20,
            }
            print(b, {k: round(v, 2) for k, v in data["bs"][str(b)].items() if k != 'peak_vram_mb'}, flush=True)
            print('  peak_mb', round(data['bs'][str(b)]['peak_vram_mb'], 1), flush=True)
            del stream
            torch.cuda.empty_cache()
        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
            data["bs"][str(b)] = {"error": repr(exc)}
            print(b, "ERROR", repr(exc), flush=True)
            torch.cuda.empty_cache()
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
