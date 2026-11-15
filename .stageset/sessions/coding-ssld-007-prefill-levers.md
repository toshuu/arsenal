---
type: CODING
time: 2026-11-15T18:29:05+05:30
summary: Add voice and first-chunk levers and measure them at B=96 and B=128 on T4.
paths: Code/batch/batched_stream.py; Code/probes/check_batch_levers.py; Code/probes/bench_batch_server.py; Code/probes/probe_prefill_levers.py; Code/probes/make_lever_quality_wavs.py; Code/probes/out/lever_quality/; Skeletons/Code/batch/batched_stream.py; .stageset/facts.md
related: IDEA-0003; SSLD-007; 20261115-182905-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Add `voice_seconds` and `max_first_tokens` to `BatchedStream`. Keep defaults unchanged.
- Cap the first chunk by token truncation. The text splitter alone does not split one long sentence.
- Add `--fp16`, `--voice-seconds`, and `--first-tokens` to the burst harness.
- Record the GPU name in the JSON so the test repeats on L4.

## Outcomes

- `CHECK-BATCH-STREAM-04` passes.
- Probe on T4: B=96 p95 is under 350 ms for every lever pair. B=128 is not stable.
- Best point: voice 4.0 s, cap 16, B=96, p95 217.5 ms.
- Quality WAVs for voice 6.5, 3.0, and 2.0 s are in `Code/probes/out/lever_quality/`.
- Run-order noise is likely. A randomized rerun is needed before a default is set.

## Follow-up

- Manual listening gate on the lever WAVs.
- Rerun the probe with random order and 3 bursts.
- Then set the default voice length and chunk cap, and recheck quality.
