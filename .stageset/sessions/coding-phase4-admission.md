---
type: CODING
time: 2026-11-22T19:23:27+05:30
summary: Run the Phase 4 admission probe with the cap raised to 640.
paths: Code/probes/probe_phase4_admission.py; Code/probes/out/phase4_admission/admission.json; .stageset/runs/20261122-192327-RUN.md; Skeletons/Probes/probe_phase4_admission.md
related: IDEA-0008; SSLD-025; 20261122-192327-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Test the cap before a `BatchedStream` change.

## Outcomes

- The probe ran. The measured values are in `20261122-192327-RUN`.

## Follow-up

- The planner reads the run report and updates the facts and IDEA-0008.
