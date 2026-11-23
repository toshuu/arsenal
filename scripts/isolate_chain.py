"""Isolate the pre-SDPA attention chain using real projected tensors."""

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
from pocket_tts.modules.attention import StreamingMultiheadAttention, _build_attention_mask

wrap, args = build()
attn = next(m for m in wrap.m.flow_lm.modules() if isinstance(m, StreamingMultiheadAttention))
state = {attn._module_absolute_name: {"offset": args[3], "pad": args[4], "cache": args[5]}}
projected = attn.in_proj(torch.randn(8, 1, attn.in_proj.in_features, device="cuda", dtype=torch.float16))


class Chain(torch.nn.Module):
    def __init__(self, module):
        super().__init__()
        self.m = module

    def forward(self, proj, offset, pad, cache):
        st = {self.m._module_absolute_name: {"offset": offset, "pad": pad, "cache": cache}}
        b, t, _ = proj.shape
        d = self.m.dim_per_head
        q = proj[..., : self.m.attn_dim].view(b, t, self.m.num_heads, d)
        kv = proj[..., self.m.attn_dim :].view(b, t, 2, self.m.num_kv_heads, d)
        k, v = torch.unbind(kv, dim=2)
        rope_offset = self.m._cache_backend.rope_offset(st[self.m._module_absolute_name], b, q.device)
        q, k = self.m.rope(q, k, offset=rope_offset)
        q = q.transpose(1, 2)
        k_attn, v_attn, pos_k, off = self.m._cache_backend.append_and_get(k, v, st[self.m._module_absolute_name])
        if self.m.num_kv_heads != self.m.num_heads:
            k_attn = k_attn.repeat_interleave(self.m.num_heads // self.m.num_kv_heads, dim=1)
            v_attn = v_attn.repeat_interleave(self.m.num_heads // self.m.num_kv_heads, dim=1)
        pos_q = off.view(-1, 1) + torch.arange(t, device=q.device, dtype=torch.long).view(1, -1)
        mask = _build_attention_mask(pos_q, pos_k, self.m.context)
        return q, k_attn, v_attn, mask


path = OUT / "chain.onnx"
module = Chain(attn).eval()
inputs = (projected, args[3].clone(), args[4].clone(), args[5].clone())
probe = module(*[t.clone() for t in inputs])
torch.onnx.export(
    module, inputs, str(path),
    input_names=[f"i{i}" for i in range(len(inputs))],
    output_names=[f"o{i}" for i in range(len(probe))],
    opset_version=17, dynamo=False, do_constant_folding=False,
)
ref = module(*[t.clone() for t in inputs])
torch.cuda.synchronize()
sess = ort.InferenceSession(str(path), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
got = sess.run(None, {f"i{i}": t.detach().cpu().numpy() for i, t in enumerate(inputs)})
for i, (g, r) in enumerate(zip(got, ref)):
    a = torch.tensor(g, device="cuda").float()
    b = r.detach().float()
    if a.shape != b.shape:
        print(i, "shape", list(a.shape), list(b.shape), flush=True)
        continue
    finite = torch.isfinite(b)
    fd = float((a[finite] - b[finite]).abs().max()) if finite.any() else 0.0
    print(i, "equal", torch.equal(a, b), "finite_diff", fd,
          "ort_nan", bool(torch.isnan(a).any()), flush=True)



import torch.nn.functional as F


class SDPA(torch.nn.Module):
    def forward(self, q, k, v, m):
        return F.scaled_dot_product_attention(q, k, v, m.to(q.dtype), dropout_p=0.0, is_causal=False)


sdpa_inputs = [torch.tensor(g, device="cuda") for g in got[:3]] + [torch.tensor(got[3], device="cuda")]
ref_sdpa = F.scaled_dot_product_attention(*[r for r in ref[:3]], ref[3].to(ref[0].dtype), dropout_p=0.0, is_causal=False)
p2 = OUT / "chain_sdpa.onnx"
torch.onnx.export(SDPA().eval(), tuple(sdpa_inputs), str(p2),
                  input_names=[f"i{i}" for i in range(4)], output_names=["o0"],
                  opset_version=17, dynamo=False, do_constant_folding=False)
s2 = ort.InferenceSession(str(p2), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
g2 = s2.run(None, {f"i{i}": t.detach().cpu().numpy() for i, t in enumerate(sdpa_inputs)})[0]
a2 = torch.tensor(g2, device="cuda").float(); b2 = ref_sdpa.float()
print("SDPA equal", torch.equal(a2, b2), "finite_diff",
      float((a2[torch.isfinite(b2)] - b2[torch.isfinite(b2)]).abs().max()),
      "ort_nan", bool(torch.isnan(a2).any()), flush=True)


mask_bool = (ref[3] == 0)
sdpa_bool_inputs = [torch.tensor(g, device="cuda") for g in got[:3]] + [mask_bool]
ref_bool = F.scaled_dot_product_attention(*[r for r in ref[:3]], mask_bool, dropout_p=0.0, is_causal=False)
p3 = OUT / "chain_sdpa_bool.onnx"
torch.onnx.export(SDPA().eval(), tuple(sdpa_bool_inputs), str(p3),
                  input_names=[f"i{i}" for i in range(4)], output_names=["o0"],
                  opset_version=17, dynamo=False, do_constant_folding=False)
s3 = ort.InferenceSession(str(p3), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
g3 = s3.run(None, {f"i{i}": t.detach().cpu().numpy() for i, t in enumerate(sdpa_bool_inputs)})[0]
a3 = torch.tensor(g3, device="cuda").float(); b3 = ref_bool.float()
print("SDPA_BOOL equal", torch.equal(a3, b3), "finite_diff",
      float((a3[torch.isfinite(b3)] - b3[torch.isfinite(b3)]).abs().max()),
      "ort_nan", bool(torch.isnan(a3).any()), flush=True)
