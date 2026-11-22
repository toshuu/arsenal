---
type: MAINTENANCE
time: 2026-11-22T20:05:00+05:30
summary: Review quiet probe. No policy passes. Early break causes [1,319].
paths: .stageset/facts.md; .stageset/runs/20261122-195737-RUN.md; Ideas/IDEA-0008-natural-live-call-streaming.md
related: IDEA-0008; FACT-0155; SSLD-028; 20261122-195737-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Remove the `active_call_sessions` early break as a direct cause. Guard it with a minimum batch size.
- Test one more code-fix probe before reporting the floor.

## Outcomes

- No policy passed at B=320. Quiet policies split `[1,319]`.

## Follow-up

- SSLD-029: add a minimum early-break guard, unit test, real B=320 confirm.
