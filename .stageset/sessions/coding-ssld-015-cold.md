---
type: CODING
time: 2026-11-16T15:10:00+05:30
summary: Cold-start probe and prewarm budget test. Boot 5.56 s. Cold p95 575-657 ms. Prewarm 633 ms, over the 100 ms budget.
paths: Code/probes/probe_cold_start.py; Code/batch/prewarm.py; LivingDocs/SSLD-015-cold-start.md; Skeletons/Probes/probe_cold_start.md; .stageset/runs/20261116-150000-RUN.md; .stageset/runs/20261116-150500-RUN.md
related: SSLD-015; IDEA-0004; FACT-0054
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Measure each cold scenario in its own child process.
- Test the prewarm against the 100 ms boot budget.

## Outcomes

- Boot 5.56 s. Weight read 1.03 s. First flow 252 ms. First decode 485 ms.
- Cold p95 575 to 657 ms and almost flat across B.
- Prewarm costs 633 ms. It fails the budget.

## Follow-up

Planner decision: accept the boot trade or accept the cold burst.
