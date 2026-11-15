# Isolated experiments (sideline)

Purpose: test TRT / ONNX / INT8 gains and samples without changing main track (`Code/batch`, probes, facts pipeline stays untouched except this folder).

## Layout
- `trt/exp_trt.py` — TensorRT feasibility/timing (if libs available).
- `onnx/exp_onnx.py` — ONNX export feasibility + runtime timing (if available).
- `int8/exp_int8.py` — INT8 quantization timing + sample WAVs (torchao/torch).
- `out/` — JSON/txt results and sample WAVs.

## Run
From repo root:
```bash
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python3 Code/experiments/int8/exp_int8.py
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python3 Code/experiments/onnx/exp_onnx.py
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python3 Code/experiments/trt/exp_trt.py
```

Results are append-only in `out/`. Main path remains `Code/batch/batched_stream.py`.
