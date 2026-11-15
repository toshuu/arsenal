---
type: CODING
time: 2026-11-15T22:35:00+05:30
summary: Add isolated TRT/ONNX/INT8 experiments (sideline, main path unchanged).
paths: Code/experiments/README.md; Code/experiments/int8/exp_int8.py; Code/experiments/onnx/exp_onnx.py; Code/experiments/trt/exp_trt.py
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Done
- INT8 (torchao `int8_weight_only` on flow_lm, B=32, 3 rounds): p50 70.72/p95 100.63 ms, wall 1.198 s vs baseline 87.24/110.88 ms, 1.091 s. Samples `Code/experiments/out/int8_baseline.wav`, `int8_torchao.wav`.
- ONNX: dummy export OK; full export blocked by stateful `ModelState` dict API; onnxruntime missing.
- TRT: `tensorrt`/`torch_tensorrt` missing; no backend.

## Rule
- Sideline only. Do not change `Code/batch/` main path.
