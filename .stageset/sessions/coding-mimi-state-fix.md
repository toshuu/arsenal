---
type: CODING
time: 2026-11-15T18:09:08+05:30
summary: Fix the missing Mimi decoder state increment that degraded batched audio.
paths: Code/batch/batched_stream.py; Code/probes/make_fp16_quality_wavs.py; Code/probes/cmp_reference_audio.py; Skeletons/Code/batch/batched_stream.py; Code/probes/out/fp16_quality/
related: IDEA-0003; 20261115-180908-RUN-mimi-state-fix; 20261115-181519-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Treat the reported audio defect as a pipeline bug, not an FP16 bug.
- Advance the Mimi state after each decode, as the reference path does.
- Add a reproducible script for the quality WAVs.

## Outcomes

- Cause: `BatchedStream` never called `increment_steps` for the Mimi decoder.
- Before the fix, batched audio vs reference corr was 0.6154.
- After the fix, corr is 0.99999.
- `check_batch_stream.py` passes.
- The nine quality WAVs are regenerated with the fixed path.
- The skeleton now has spec_revision 2 and CHECK-BATCH-STREAM-03.

## Follow-up

- Manual listening gate on the new WAVs.
- Record PASS or FAIL in facts.
