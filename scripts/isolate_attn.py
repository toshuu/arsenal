"""Isolate the exact attention op that diverges in ONNX Runtime."""

from __future__ import annotations

import sys
from pathlib import Path

import onnxruntime as ort
import torch

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "isolate"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "vendor" / "pocket-tts"))
from flow_model import build
import pocket_tts.modules.attention as attnmod
import torch.nn.functional as F

wrap, args = build()
from pocket_tts.modules.attention import StreamingMultiheadAttention
attn = next(m for m in wrap.m.flow_lm.modules() if isinstance(m, StreamingMultiheadAttention))
offset = args[3].clone()
pad = args[4].clone()
cache = args[5].clone()
print("offset", offset[:3], "pad", pad[:3], "cache", tuple(cache.shape), flush=True)


def compare(name, module, module_args):
    path = OUT / f"{name}.onnx"
    probe = module(*[t.clone() for t in module_args])
    nout = len(probe) if isinstance(probe, tuple) else 1
    torch.onnx.export(
        module, module_args, str(path),
        input_names=[f"i{i}" for i in range(len(module_args))],
        output_names=[f"o{i}" for i in range(nout)],
        opset_version=17, dynamo=False, do_constant_folding=False,
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


class KV(torch.nn.Module):
    def forward(self, cache, offset, k, v):
        return attnmod.complete_kv(cache, offset, k, v)


k = torch.randn(8, 1, 16, 64, device="cuda", dtype=torch.float16)
v = torch.randn_like(k)
compare("complete_kv", KV().eval(), (cache, offset, k, v))


class Mask(torch.nn.Module):
    def forward(self, pos_q, pos_k):
        return attnmod._build_attention_mask(pos_q, pos_k, 16)


pos_q = offset.view(-1, 1).float() + torch.arange(1, device="cuda").view(1, -1).float()
pos_k = torch.arange(cache.shape[2], device="cuda").view(1, -1).expand(8, -1).float()
compare("mask", Mask().eval(), (pos_q, pos_k))


class SDPA(torch.nn.Module):
    def forward(self, q, kk, vv, mask):
        return F.scaled_dot_product_attention(q, kk, vv, mask, dropout_p=0.0, is_causal=False)


q = torch.randn(8, 16, 1, 64, device="cuda", dtype=torch.float16)
kk = torch.randn(8, 16, 165, 64, device="cuda", dtype=torch.float16)
vv = torch.randn_like(kk)
mask = attnmod._build_attention_mask(
    (offset.view(-1, 1).float() + torch.arange(1, device="cuda").view(1, -1).float()),
    torch.arange(165, device="cuda").view(1, -1).expand(8, -1).float(), 16,
).to(torch.float16)
compare("sdpa", SDPA().eval(), (q, kk, vv, mask))


class Rope(torch.nn.Module):
    def __init__(self, module):
        super().__init__()
        self.m = module

    def forward(self, q, k, offset):
        return self.m(q, k, offset)


from pocket_tts.modules.attention import _LinearKVCacheBackend

rq = torch.randn(8, 1, 16, 64, device="cuda", dtype=torch.float16)
rk = torch.randn_like(rq)
compare("rope", Rope(attn.rope).eval(), (rq, rk, offset.view(-1)[0].clone()))


class Append(torch.nn.Module):
    def __init__(self, backend):
        super().__init__()
        self.b = backend

    def forward(self, k, v, cache, offset, pad):
        return self.b.append_and_get(k, v, {"cache": cache, "offset": offset, "pad": pad})


compare("append", Append(attn._cache_backend).eval(),
        (k, v, cache.clone(), offset.clone(), pad.clone()))


class Linear(torch.nn.Module):
    def __init__(self, layer):
        super().__init__()
        self.l = layer

    def forward(self, x):
        return self.l(x)


xin = torch.randn(8, 1, attn.in_proj.in_features, device="cuda", dtype=torch.float16)
compare("in_proj", Linear(attn.in_proj).eval(), (xin,))
proj = attn.in_proj(xin)
d = attn.dim_per_head
qpart = proj[..., : attn.attn_dim].view(8, 1, attn.num_heads, d)
kv = proj[..., attn.attn_dim :].view(8, 1, 2, attn.num_kv_heads, d)
kk2, vv2 = torch.unbind(kv, dim=2)
compare("q_view", torch.nn.Identity(), (qpart,))
xout = torch.randn(8, 1, attn.out_proj.in_features, device="cuda", dtype=torch.float16)
compare("out_proj", Linear(attn.out_proj).eval(), (xout,))
