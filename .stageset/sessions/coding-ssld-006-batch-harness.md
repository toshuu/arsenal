---
type: CODING
time: 2026-11-15T14:19:32+05:00
summary: Measure the Phase B lockstep batch ceiling with unique texts and B=32 parity.
paths: Code/probes/bench_batch_server.py; Skeletons/Probes/bench_batch_server.md; Code/probes/out/bench_batch_server_knee.json
related: SSLD-006; IDEA-0003; SSLD-005
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use 5 bursts for the knee run, not 3. The tail is noisy.
- Treat the p95 target as met at B=32, but recommend B=30 for production headroom.
- Keep the first text chunk only. The probe texts are one sentence and one chunk.

## Outcomes

- B=30: p95 278.8 ms, 149/150 under 350 ms, max 375.8 ms, 2.42 s wall, RTF 0.013.
- B=32: p95 327.0 ms, 156/160 under 350 ms, max 404.8 ms, 2.56 s wall, RTF 0.013.
- B=34: p95 359.7 ms in the latest run. It passed at 295.0 ms in an earlier run, so it is unstable.
- B=35 and B=36: p95 358.5 and 357.6 ms. Fail.
- B=32 parity: 1.07e-04 max absolute difference and correlation 1.0 versus B=1.
- Peak VRAM at B=32: 2247 MB.
- The Phase B target of 32 on one T4 is met on p95. B=30 is the safer operating point.

## Follow-up

- Update the burst report and strategy with the Phase B numbers.
- Run S1 FP16 as the Phase C spike. Do not start TensorRT or ONNX.
