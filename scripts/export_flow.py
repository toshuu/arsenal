"""Export the patched flow step with torch.export (no ONNX runtime needed)."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import torch

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "export"
OUT.mkdir(parents=True, exist_ok=True)
logging.disable(logging.CRITICAL)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

sys.path.insert(0, str(ROOT / "vendor" / "pocket-tts"))
sys.path.insert(0, str(ROOT / "Code"))
sys.path.insert(0, str(ROOT / "Code" / "probes"))
os.chdir(ROOT / "Code" / "model")

from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream, set_state_padding
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights
from pocket_tts.modules.stateful_module import init_states
from bench_batch_server import make_texts

BATCH = 8
FRAMES = 64
result: dict = {"batch": BATCH, "frames": FRAMES}

model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
enable_fp16_backbone(model, mimi_fp16=True)
load_fp16_weights(model, Path("fp16_weights.pt"))
model.temp = 0.0
sp = BatchedStream(
    model, voice="/kaggle/working/refHD.wav", voice_seconds=4.0, max_first_tokens=16
)
prefix, pad, _ = sp._build_prefixes(make_texts(BATCH)[:BATCH])
state = init_states(model.flow_lm, BATCH, 512)
set_state_padding(state, pad)
names = list(state.keys())


class FlowStep(torch.nn.Module):
    def __init__(self, model, names):
        super().__init__()
        self.m = model
        self.names = names

    def forward(self, text_tokens, latent, audio_cond, *flat):
        st = {}
        i = 0
        for n in self.names:
            st[n] = {"offset": flat[i], "pad": flat[i + 1], "cache": flat[i + 2]}
            i += 3
        out, eos = self.m._run_flow_lm_and_increment_step(st, text_tokens, latent, audio_cond)
        outs = [out, eos]
        for n in self.names:
            outs.extend([st[n]["offset"], st[n]["pad"], st[n]["cache"]])
        return tuple(outs)


wrap = FlowStep(model, names).eval()
flat = []
for n in names:
    for key in ("offset", "pad", "cache"):
        flat.append(state[n][key])
empty_tokens = torch.empty(BATCH, 0, dtype=torch.int64, device="cuda")
latent = model.flow_lm.bos_emb.view(1, 1, -1).expand(BATCH, 1, -1)
args = (empty_tokens, latent, prefix) + tuple(flat)
try:
    ep = torch.export.export(wrap, args, strict=True)
    torch.export.save(ep, OUT / "flow_step.pt2")
    torch.save(tuple(args), OUT / "flow_inputs.pt")
    result["export"] = "ok"
    result["graph_size"] = len(str(ep.graph_module.graph))
except Exception as exc:
    result["export"] = "FAIL"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:1200]}"
(OUT / "export_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("EXPORT_DONE", json.dumps(result)[:1500])
sys.exit(0 if result["export"] == "ok" else 1)
