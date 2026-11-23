"""Build a TensorRT engine from the patched flow-step ONNX graph."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import tensorrt as trt

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
OUT = ROOT / "out" / "export"
FP32 = os.getenv("TRT_FP32") == "1"
ONNX = OUT / (os.getenv("TRT_ONNX") or "flow_step.onnx")
ENGINE = OUT / (os.getenv("TRT_ENGINE") or ("flow_step_fp32.engine" if FP32 else "flow_step.engine"))
result: dict = {}

logger = trt.Logger(trt.Logger.WARNING)
builder = trt.Builder(logger)
network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
parser = trt.OnnxParser(network, logger)
ok = parser.parse(ONNX.read_bytes())
result["parse"] = bool(ok)
if not ok:
    result["errors"] = [parser.get_error(i).desc()[:400] for i in range(parser.num_errors)]
else:
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)
    if not FP32:
        config.set_flag(trt.BuilderFlag.FP16)
    start = time.time()
    try:
        engine = builder.build_serialized_network(network, config)
        result["build"] = bool(engine)
        result["build_s"] = round(time.time() - start, 2)
        if engine:
            serialized = bytes(engine)
            ENGINE.write_bytes(serialized)
            result["bytes"] = len(serialized)
    except Exception as exc:
        result["build"] = False
        result["error"] = f"{type(exc).__name__}: {str(exc)[:1500]}"
        result["build_s"] = round(time.time() - start, 2)
(OUT / "engine_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("ENGINE_DONE", json.dumps(result)[:2500])
raise SystemExit(0 if result.get("build") else 1)
