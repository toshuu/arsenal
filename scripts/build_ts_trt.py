"""Try TorchScript IR TRT compile for the patched flow step."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch
import torch_tensorrt

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "export"
sys.path.insert(0, str(ROOT / "scripts"))
from flow_model import build

result = {}
wrap, args = build()
try:
    traced = torch.jit.trace(wrap, args, strict=False, check_trace=False)
    result["trace"] = "ok"
except Exception as exc:
    result["trace"] = "FAIL"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:1200]}"
    (OUT / "ts_trt_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("TS_TRT_DONE", json.dumps(result)[:1500])
    raise SystemExit(1)

start = time.time()
try:
    compiled = torch_tensorrt.compile(
        traced,
        ir="torchscript",
        inputs=[torch_tensorrt.Input(shape=tuple(t.shape), dtype=t.dtype) for t in args],
        enabled_precisions={torch.float16},
        workspace_size=1 << 30,
        min_block_size=1,
        require_full_compilation=False,
        truncate_long_and_double=True,
        torch_executed_ops=[
            "aten::scaled_dot_product_attention",
            "aten::_scaled_dot_product_attention",
            "aten::_scaled_dot_product_flash_attention",
            "aten::_scaled_dot_product_efficient_attention",
        ],
    )
    result["build"] = "ok"
    result["build_s"] = round(time.time() - start, 2)
    out = compiled(*[t.clone() for t in args])
    torch.cuda.synchronize()
    ref = wrap(*[t.clone() for t in args])
    torch.cuda.synchronize()
    a, b = out[0].float(), ref[0].float()
    result["maxdiff"] = float((a - b).abs().max())
    result["mae"] = float((a - b).abs().mean())
    result["corr"] = float(torch.corrcoef(torch.stack([a.flatten(), b.flatten()]))[0, 1])
    result["eos_match"] = bool(torch.equal(out[1], ref[1]))
except Exception as exc:
    import traceback
    result["build"] = "FAIL"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:1500]}"
    result["traceback"] = traceback.format_exc()[-2000:]
    result["build_s"] = round(time.time() - start, 2)
(OUT / "ts_trt_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("TS_TRT_DONE", json.dumps(result)[:2500])
