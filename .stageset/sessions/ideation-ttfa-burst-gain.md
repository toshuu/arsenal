---
type: IDEATION
time: 2026-11-16T07:30:00+05:30
summary: Plan E0 stage-timestamp probe to explain the 50 to 180 ms TTFA gap.
paths: Ideas/IDEA-0004-ttfa-burst-gain.md; Ideas/_index.md; Skeletons/Code/batch/batched_stream.py; Skeletons/Probes/probe_ttfa_stages.md
related: IDEA-0004; IDEA-0003; FACT-0041; SSLD-010
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Accept the ranked gain plan from the user as IDEA-0004.
- Do E0 before any other lever. All later choices depend on its data.
- Add a cheap `on_stage` callback to `BatchedStream.stream()`. Do not
  restructure the hot path in this revision.
- Run the load generator in a separate process to remove CPU bias.

## Outcomes

- Skeleton revision 5 adds the stage callback contract and CHECK-BATCH-STREAM-06.
- New probe skeleton `Skeletons/Probes/probe_ttfa_stages.md` defines the measurement.

## Follow-up

- Implement the callback.
- Write and run `Code/probes/probe_ttfa_stages.py` at B=128 and B=160.
- Record stage facts and pick the next lever.
