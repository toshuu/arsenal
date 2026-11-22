---
type: CODING
time: 2026-11-22T19:37:29+05:30
summary: Run the Phase 4 formation policy probe on the local T4.
paths: Code/probes/probe_phase4_formation.py; Code/probes/out/phase4_formation/formation.json; .stageset/runs/20261122-193729-RUN.md; Skeletons/Probes/probe_phase4_formation.md
related: IDEA-0008; SSLD-026; FACT-0152; 20261122-193729-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Test four `call_first` formation policies at cap 640.

## Outcomes

- The probe ran. The measured values are in `20261122-193729-RUN`.

## Follow-up

- The planner reads the run report and picks the policy.
