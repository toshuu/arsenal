"""Run the TRT engine, check numeric parity, and benchmark against eager."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import torch
import tensorrt as trt

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "export"
result: dict = {}

engine = trt.Runtime(trt.Logger(trt.Logger.WARNING)).deserialize_cuda_engine(
    (OUT / "flow_step.engine").read_bytes()
)
ctx = engine.create_execution_context()
names = [engine.get_tensor_name(i) for i in range(engine.num_io_tensors)]
inputs = [n for n in names if engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT]
outputs = [n for n in names if engine.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT]

DT = {
    trt.DataType.HALF: torch.float16,
    trt.DataType.FLOAT: torch.float32,
    trt.DataType.INT32: torch.int32,
    trt.DataType.INT64: torch.int64,
    trt.DataType.BOOL: torch.bool,
}


def make_buffers():
    args = list(torch.load(OUT / "flow_inputs.pt", weights_only=False, map_location="cuda"))
    args = [t.contiguous() for t in args]
    outs = [
        torch.empty(tuple(engine.get_tensor_shape(n)), dtype=DT[engine.get_tensor_dtype(n)], device="cuda")
        for n in outputs
    ]
    return args, outs


def run_trt(args, outs):
    bindings = [t.data_ptr() for t in args] + [t.data_ptr() for t in outs]
    ctx.execute_v2(bindings)
    torch.cuda.synchronize()
    return outs


import sys
sys.path.insert(0, str(ROOT / "scripts"))
from flow_model import build

eager, saved_args = build()
args, outs = make_buffers()
ref = eager(*tuple(t.clone() for t in saved_args))
run_trt(args, outs)
torch.cuda.synchronize()
a = outs[0].float()
b = ref[0].float()
result["parity_out_maxdiff"] = float((a - b).abs().max())
result["parity_out_mae"] = float((a - b).abs().mean())
result["eos_match"] = bool(torch.equal(outs[1], ref[1]))
result["ref_shape"] = list(ref[0].shape)
result["trt_shape"] = list(outs[0].shape)

def bench(fn, n=60):
    for _ in range(10):
        fn()
    torch.cuda.synchronize()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        torch.cuda.synchronize()
        times.append((time.perf_counter() - t0) * 1000.0)
    return {"p50": statistics.median(times), "p95": sorted(times)[int(len(times) * 0.95)]}

a2, o2 = make_buffers()
result["trt_ms"] = bench(lambda: run_trt(a2, o2))
a3, _ = make_buffers()
result["eager_ms"] = bench(lambda: eager(*a3))
result["speedup"] = round(result["eager_ms"]["p50"] / result["trt_ms"]["p50"], 3)
(OUT / "bench_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("BENCH_DONE", json.dumps(result))
