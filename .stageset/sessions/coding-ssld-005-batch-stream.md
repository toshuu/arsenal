---
type: CODING
time: 2026-11-15T14:15:28+05:00
summary: Implement the Phase B lockstep batched streaming core and its parity check.
paths: Code/batch/__init__.py; Code/batch/batched_stream.py; Code/probes/check_batch_stream.py; Skeletons/Batch/batched_stream.md
related: SSLD-005; IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep the first text chunk only for Phase B.
- Measure parity as B=1 batch versus B=3 batch at temperature 0.
- Keep the module free of server concerns: no queues, no HTTP, no threads.

## Outcomes

- `Code/batch/batched_stream.py` runs one lockstep batch and streams per row.
- `python Code/probes/check_batch_stream.py` prints `CHECK_BATCH_STREAM PASS`.
- Measured parity B=1 vs B=3: 3.2e-05 max absolute difference.
- Measured first sound for three rows: 29.8 ms, 29.8 ms, 65.4 ms.

## Follow-up

- Build the burst probe for unique texts and find the p95 N.
- Do not add TensorRT, ONNX, shared voice KV, or per-row RoPE.
