---
type: CODING
time: 2026-11-22T20:12:00+05:30
summary: Guard quiet early break and test B=320 formation.
paths: Code/batch/server.py; Code/probes/probe_phase4_quiet_fix.py; Code/probes/out/phase4_quiet_fix/fix.json; .stageset/runs/20261122-200804-RUN.md
related: IDEA-0008; SSLD-029; FACT-0156; 20261122-200804-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Added `ARSENAL_CALL_FIRST_MIN_EARLY` default 32.
- Required `len(batch) >= min_early` before quiet dispatch.

## Outcomes

- FAIL. No policy passed all warm B=320 rows under 350 ms.

## Follow-up

- Lock B=224 sentence operating point; next B=320 work needs arrival control.
