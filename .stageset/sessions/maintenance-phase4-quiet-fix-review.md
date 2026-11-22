---
type: MAINTENANCE
time: 2026-11-22T20:20:00+05:30
summary: Quiet fix probe failed. Lock B=224 sentence as 350 ms operating point.
paths: .stageset/facts.md; .stageset/runs/20261122-200804-RUN.md; Ideas/IDEA-0008-natural-live-call-streaming.md; Code/batch/server.py
related: IDEA-0008; FACT-0156; SSLD-029; 20261122-200804-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- B=320 is not a stable 350 ms point on one T4 with current admission.
- Accept B=224 sentence as 350 ms operating point. Mark utterance B=224 borderline.

## Outcomes

- Min-early guard removed 1-row split. Small early splits remain.
- FACT-0156 recorded.

## Follow-up

- If owner wants B=320, next work is arrival-shape/pre-connect, not collector tuning.
