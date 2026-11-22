---
type: CODING
time: 2026-11-22T20:00:00+05:30
summary: Run the Phase 4 quiet formation probe at B=320.
paths: Code/probes/probe_phase4_quiet.py; Code/probes/out/phase4_quiet/quiet.json; .stageset/runs/20261122-195737-RUN.md; Skeletons/Probes/probe_phase4_quiet.md
related: IDEA-0008; SSLD-028; FACT-0155; 20261122-195737-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Test 4 formation policies at B=320. Buckets off.

## Outcomes

- FAIL. No policy passed. Quiet split `[1,319]`. See `20261122-195737-RUN`.

## Follow-up

- Fix the quiet early-break guard. Re-test.
