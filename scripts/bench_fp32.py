"""Benchmark TRT FP32 engine against FP32 eager on the flow step."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import torch
import tensorrt as trt

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "export"
sys.path.insert(0, str(ROOT / "scripts"))
from flow_model_fp32 import build

eager, _ = build()
engine = trt.Runtime(trt.Logger(trt.Logger.WARNING)).deserialize_cuda_engine(
    (OUT / "flow_step_fp32graph.engine").read_bytes()
)
ctx = engine.create_execution_context()
names = [engine.get_tensor_name(i) for i in range(engine.num_io_tensors)]
outs_names = [n for n in names if engine.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT]
DT = {trt.DataType.FLOAT: torch.float32, trt.DataType.INT64: torch.int64,
      trt.DataType.HALF: torch.float16, trt.DataType.BOOL: torch.bool}


def fresh():
    args = [t.detach().contiguous() for t in torch.load(OUT / "flow_inputs_fp32.pt", weights_only=False, map_location="cuda")]
    outs = [torch.empty(tuple(engine.get_tensor_shape(n)), dtype=DT[engine.get_tensor_dtype(n)], device="cuda")
            for n in outs_names]
    return args, outs


def bench(fn, n=40):
    for _ in range(5):
        fn()
    torch.cuda.synchronize()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        torch.cuda.synchronize()
        times.append((time.perf_counter() - t0) * 1000.0)
    return {"p50": round(statistics.median(times), 3),
            "p95": round(sorted(times)[int(len(times) * 0.95)], 3)}


def run_trt():
    a, o = fresh()
    ctx.execute_v2([t.data_ptr() for t in a] + [t.data_ptr() for t in o])
    torch.cuda.synchronize()


def run_eager():
    a, _ = fresh()
    eager(*a)
    torch.cuda.synchronize()


import os
mode = os.getenv("BENCH_MODE", "both")
result = {}
if mode in ("both", "trt"):
    result["trt_ms"] = bench(run_trt)
if mode in ("both", "eager"):
    result["eager_ms"] = bench(run_eager)
if "trt_ms" in result and "eager_ms" in result:
    result["speedup"] = round(result["eager_ms"]["p50"] / result["trt_ms"]["p50"], 3)
(OUT / "bench_fp32_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("BENCH", json.dumps(result))
