---
type: CODING
time: 2026-11-15T18:33:37+05:30
summary: Record the lever quality listening gate as PASS.
paths: Code/probes/out/lever_quality/; .stageset/runs/20261115-183337-RUN.md; .stageset/facts.md
related: IDEA-0003; SSLD-007; 20261115-183337-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Accept the lever WAVs. Keep FP32 and FP16.
- Do not set one voice length as the default until the randomized probe runs.

## Outcomes

- Owner listened to the six lever WAVs.
- The owner reported that they worked.
- FACT-0018 records the gate result.

## Follow-up

- Run the randomized 3-burst probe.
- Choose the default voice length and first-chunk cap.
- Then run B=128 and Phase D RTF work.
