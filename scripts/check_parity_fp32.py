"""Minimal one-shot parity check between eager and TRT flow step."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import torch

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "export"
sys.path.insert(0, str(ROOT / "scripts"))
from flow_model_fp32 import build

eager, saved = build()
args = [t.clone().contiguous() for t in saved]
ref = eager(*args)
torch.cuda.synchronize()
print("EAGER_OK", ref[0].shape, float(ref[0].abs().max()), flush=True)

import tensorrt as trt

engine_name = os.getenv("TRT_ENGINE") or "flow_step.engine"
engine = trt.Runtime(trt.Logger(trt.Logger.WARNING)).deserialize_cuda_engine(
    (OUT / engine_name).read_bytes()
)
ctx = engine.create_execution_context()
names = [engine.get_tensor_name(i) for i in range(engine.num_io_tensors)]
ins = [n for n in names if engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT]
outs_names = [n for n in names if engine.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT]
DT = {
    trt.DataType.HALF: torch.float16,
    trt.DataType.FLOAT: torch.float32,
    trt.DataType.INT32: torch.int32,
    trt.DataType.INT64: torch.int64,
    trt.DataType.BOOL: torch.bool,
}
a2 = [t.clone().contiguous() for t in saved]
o2 = [
    torch.empty(tuple(engine.get_tensor_shape(n)), dtype=DT[engine.get_tensor_dtype(n)], device="cuda")
    for n in outs_names
]
ctx.execute_v2([t.data_ptr() for t in a2] + [t.data_ptr() for t in o2])
torch.cuda.synchronize()
print("TRT_OK", o2[0].shape, float(o2[0].abs().max()), flush=True)
a = o2[0].float()
b = ref[0].float()
res = {
    "maxdiff": float((a - b).abs().max()),
    "mae": float((a - b).abs().mean()),
    "eos_match": bool(torch.equal(o2[1], ref[1])),
    "corr": float(torch.corrcoef(torch.stack([a.flatten(), b.flatten()]))[0, 1]),
}
res_name = os.getenv("TRT_PARITY_OUT") or "parity_result.json"
(OUT / res_name).write_text(json.dumps(res, indent=2), encoding="utf-8")
print("PARITY", json.dumps(res), flush=True)
