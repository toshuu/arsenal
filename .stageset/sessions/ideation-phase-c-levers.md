---
type: IDEATION
time: 2026-11-15T18:20:00+05:30
summary: Plan Phase C prefill levers and per-GPU reproduction on T4 and L4.
paths: Ideas/optimization-strategy.md; Skeletons/Code/batch/batched_stream.py; Skeletons/Probes/bench_batch_server.md; Skeletons/Probes/probe_prefill_levers.md
related: IDEA-0003; FACT-0016
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Phase C starts with V4 (voice length) and V5 (first-chunk cap).
- Add `voice_seconds` and `max_first_tokens` to `BatchedStream`.
- Add `--fp16`, `--voice-seconds`, and `--first-tokens` to the burst harness.
- Probe voice lengths 6.5, 4, 3, 2 seconds and chunk caps 50, 24, 16 at B=96 and B=128.
- Record the GPU name in every result. Repeat the same probe on L4 later.
- Keep the default behavior unchanged until the listening gate passes.

## Outcomes

- Skeleton rev 3 for `batched_stream.py`.
- Probe skeleton rev 2 for the harness.
- New probe skeleton `probe_prefill_levers`.

## Follow-up

- Write SSLD-007 and run it.
