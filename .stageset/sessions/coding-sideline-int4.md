---
type: CODING
time: 2026-11-15T23:10:00+05:30
summary: Try sideline INT4 (torchao) on flow_lm; all attempts fail.
paths: Code/experiments/int4/exp_int4.py; Code/experiments/out/int4_summary.json
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Done
- INT4 attempts (torchao 0.10.0, T4 sm75, FP16 backbone): `Int4WeightOnlyConfig` g64/g128 fail with dtype error (`zeros` expected float32, got bfloat16). g32 fails with `CUDA error: named symbol not found`. No INT4 model run, no INT4 sample.
- Baseline in same run: p50 65.61, p95 117.9 ms, wall 1.037 s, 96/96 <350 (B=32, cond cap16). Output: `Code/experiments/out/int4_*`.
