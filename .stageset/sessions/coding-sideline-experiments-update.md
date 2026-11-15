---
type: CODING
time: 2026-11-15T22:50:00+05:30
summary: Update ONNX sideline with ORT install and full-export failure detail.
paths: Code/experiments/onnx/exp_onnx.py; Code/experiments/out/onnx_summary.json
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Done
- Installed `onnxruntime-gpu` (CUDA EP available). Dummy ONNX export/run OK (~0.05 ms).
- Full `flow_lm` step export (`torch.export`) failed: data-dependent guard `Eq(u0,1)` in attention/cache + stateful ModelState dict I/O. No end-to-end ONNX path, no sample, no gain.
- INT8 benefit (FACT-0036 context): lower weight memory/bandwidth (capacity headroom); TTFA p95 lower in test (100.6 vs 110.9 ms) but wall/RTF worse (1.198 vs 1.091 s) from quant overhead — not a throughput win on T4 FP16. Quality: ear check pass reported.
