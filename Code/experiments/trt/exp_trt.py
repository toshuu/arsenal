"""Isolated TensorRT experiment: feasibility/timing if available."""
import json, os, sys, subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "Code" / "experiments" / "out"
OUT.mkdir(parents=True, exist_ok=True)
res = {"tensorrt": False, "torch_tensorrt": False, "compile_backend": None, "notes": []}

try:
    import tensorrt as trt
    res["tensorrt"] = trt.__version__
except Exception as e:
    res["notes"].append(f"tensorrt import failed: {e}")

try:
    import torch_tensorrt
    res["torch_tensorrt"] = getattr(torch_tensorrt, '__version__', 'ok')
except Exception as e:
    res["notes"].append(f"torch_tensorrt import failed: {e}")

try:
    import torch
    # check if backend registered
    backends = getattr(torch._dynamo.list_backends(), '__iter__', None)
    try:
        blist = torch._dynamo.list_backends()
        res["dynamo_backends"] = [b for b in blist if 'tensorrt' in b.lower() or 'trt' in b.lower()]
    except Exception as e:
        res["notes"].append(f"list_backends: {e}")
except Exception as e:
    res["notes"].append(str(e))

res["notes"].append("TensorRT libs not present in env. Sideline install/engine build not attempted to avoid breaking main env; add onnx->trt or torch_tensorrt when wheels available for this CUDA/PyTorch.")
(OUT / "trt_summary.json").write_text(json.dumps(res, indent=2) + "\n")
print("TRT_DONE", json.dumps(res))
