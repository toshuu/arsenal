"""Find the first subgraph that diverges between eager and ONNX Runtime."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "isolate"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
from flow_model import build

eager, args = build()
model = eager.m
flow = model.flow_lm


def compare(name, module, module_args):
    path = OUT / f"{name}.onnx"
    probe = module(*[t.clone() for t in module_args])
    nout = len(probe) if isinstance(probe, tuple) else 1
    torch.onnx.export(
        module,
        module_args,
        str(path),
        input_names=[f"i{i}" for i in range(len(module_args))],
        output_names=[f"o{i}" for i in range(nout)],
        opset_version=17,
        dynamo=False,
        do_constant_folding=False,
    )
    ref = module(*[t.clone() for t in module_args])
    torch.cuda.synchronize()
    sess = ort.InferenceSession(str(path), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    got = sess.run(None, {f"i{i}": t.detach().cpu().numpy() for i, t in enumerate(module_args)})
    refs = ref if isinstance(ref, tuple) else (ref,)
    print("==", name, flush=True)
    for i, (g, r) in enumerate(zip(got, refs)):
        a = torch.tensor(g, device="cuda").float()
        b = r.detach().float()
        if a.shape != b.shape:
            print(i, "shape", list(a.shape), list(b.shape), flush=True)
            continue
        equal = torch.equal(a, b)
        finite = torch.isfinite(b)
        finite_diff = float((a[finite] - b[finite]).abs().max()) if finite.any() else 0.0
        print(i, "equal", equal, "finite_diff", finite_diff,
              "ort_nan", bool(torch.isnan(a).any()), "ref_nan", bool(torch.isnan(b).any()), flush=True)


class Cond(torch.nn.Module):
    def __init__(self, lm):
        super().__init__()
        self.lm = lm

    def forward(self, tokens, audio):
        e = self.lm.conditioner(tokens)
        return torch.cat([e, audio], dim=1)


compare("cond", Cond(flow).eval(), (args[0].clone(), args[2].clone()))

from pocket_tts.modules.attention import StreamingMultiheadAttention

attn = None
attn_name = None
for name, module in flow.named_modules():
    if isinstance(module, StreamingMultiheadAttention):
        attn, attn_name = module, name
        break
print("ATTN", attn_name, flush=True)


class Attn(torch.nn.Module):
    def __init__(self, module, name):
        super().__init__()
        self.m = module
        self.name = name

    def forward(self, x, offset, pad, cache):
        state = {self.name: {"offset": offset, "pad": pad, "cache": cache}}
        projected = self.m.in_proj(x)
        out = self.m(x, state)
        return projected, out


st = {}
i = 3
from flow_model import FlowStep
for n in eager.names:
    st[n] = {"offset": args[i], "pad": args[i + 1], "cache": args[i + 2]}
    i += 3
s = st[attn_name]
hidden = attn.in_proj.in_features
x = torch.randn(8, 1, hidden, device="cuda", dtype=torch.float16)
compare("attn", Attn(attn, attn_name).eval(), (x, s["offset"].clone(), s["pad"].clone(), s["cache"].clone()))
