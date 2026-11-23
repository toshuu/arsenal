"""Build a TensorRT engine from the exported patched flow step."""

from __future__ import annotations

import json
import time
from pathlib import Path

import torch
import torch_tensorrt

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
EP_PATH = ROOT / "out" / "export" / "flow_step.pt2"
OUT = ROOT / "out" / "export"
result: dict = {}

try:
    ep = torch.export.load(EP_PATH)
    result["load"] = "ok"
except Exception as exc:
    result["load"] = "FAIL"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:1200]}"
    (OUT / "trt_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("TRT_DONE", json.dumps(result)[:1500])
    raise SystemExit(1)

args = list(torch.load(OUT / "flow_inputs.pt", weights_only=False, map_location="cuda"))
print("INPUTS", len(args), flush=True)

start = time.time()
try:
    compiled = torch_tensorrt.dynamo.compile(
        ep,
        arg_inputs=[tuple(args)],
        device="cuda:0",
        enabled_precisions={torch.float16},
        workspace_size=1 << 30,
        min_block_size=1,
        require_full_compilation=False,
        pass_through_build_failures=False,
        optimization_level=3,
        num_avg_timing_iters=2,
        use_explicit_typing=False,
    )
    result["build"] = "ok"
    result["build_s"] = round(time.time() - start, 2)
    out1 = compiled(*tuple(args))
    torch.cuda.synchronize()
    result["run"] = "ok"
    result["out_shapes"] = [list(o.shape) for o in out1[:2]]
except Exception as exc:
    import traceback
    result["build"] = "FAIL"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:2000]}"
    result["traceback"] = traceback.format_exc()[-3000:]
    result["build_s"] = round(time.time() - start, 2)

(OUT / "trt_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("TRT_DONE", json.dumps(result)[:2500])
raise SystemExit(0 if result.get("build") == "ok" else 1)
