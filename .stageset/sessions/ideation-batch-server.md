---
type: IDEATION
time: 2026-11-15T14:07:25+05:30
summary: Choose a single-process lockstep batched streaming core for Phase B.
paths: Ideas/optimization-strategy.md; Skeletons/Batch/batched_stream.md; Code/batch/batched_stream.py
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use one process, one model copy, and one lockstep batch per GPU.
- Build the prefix as a right-aligned `[BOS, voice, text]` tensor and set `pad` on the flow state.
- Batch the Mimi decoder and emit one frame per step for all active rows.
- Keep the first text chunk only for Phase B. Full multi-chunk generation is deferred.
- Do not use TensorRT, ONNX, shared voice KV, or per-row RoPE in Phase B.

## Outcomes

- Skeleton `Skeletons/Batch/batched_stream.md` is READY for implementation.
- SSLD-005 is the implementation plan.

## Follow-up

- Execute SSLD-005, then build the burst harness for unique mixed-length texts.
