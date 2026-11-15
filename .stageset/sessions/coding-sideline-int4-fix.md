---
type: CODING
time: 2026-11-15T23:30:00+05:30
summary: Web-search and retry INT4 fixes (torchao 0.10, T4); no working path.
paths: Code/experiments/int4/exp_int4_fix.py; Code/experiments/out/int4_fix_summary.json
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Done
- Web search: tinygemm int4 weight-only often unsupported/problematic on T4 (sm75), can raise `named symbol not found`; some APIs need BF16/tile packing. torchao 0.10 config API differs from newer docs.
- Fix attempts: `hqq`/`tile_packed_to_4d` args rejected by local API; v1 on CPU fp32 failed (`aten::_convert_weight_to_int4pack` not on CPU). No successful INT4 quant/infer, no sample.
- Baseline same run: p50 57.92, p95 102.56 ms, wall 0.988 s (B=32 cond cap16).
