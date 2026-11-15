---
type: IDEATION
time: 2026-11-15T18:55:00+05:30
summary: Plan the Phase C cleanup: cut before pause and in-process lever probe.
paths: Skeletons/Code/batch/batched_stream.py; Skeletons/Probes/probe_levers_inproc.md; Ideas/optimization-strategy.md
related: IDEA-0003; FACT-0020; SSLD-009
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Cut the voice to `voice_seconds` first. Then call `end_on_pause`.
- Compare all lever configs in one process with interleaved rounds.
- Keep `max_first_tokens=None` as the code default.
- Use the clean probe to set the serving operating point, not the code default.

## Outcomes

- Skeleton rev 4 for `batched_stream.py` with CHECK-BATCH-STREAM-05.
- New probe skeleton `probe_levers_inproc`.

## Follow-up

- Write and run SSLD-009.
