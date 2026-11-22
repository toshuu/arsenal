---
type: MAINTENANCE
time: 2026-11-22T19:49:29+05:30
summary: Review the formation probe. The default policy is stable but slow. Confirm on a real server.
paths: .stageset/facts.md; .stageset/runs/20261122-193729-RUN.md; Ideas/IDEA-0008-natural-live-call-streaming.md
related: IDEA-0008; FACT-0153; SSLD-026; 20261122-193729-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- The in-process p95 is not a gate. Confirm on a separate-process server.
- The default window of 150 ms gives one batch at all B. Use it as the baseline.
- The quiet policies are not stable at B=448. Do not wire them yet.
- The next probe uses the default window. It does not pass the `window` value.

## Outcomes

- Added FACT-0153 from `20261122-193729-RUN`.
- The run report winner line used ANY warm row. Only `q2h30` `utterance` B=320
  had all warm rows single-batch under 350 ms.

## Follow-up

- Write a real-server confirmation probe for `sentence` and `utterance` at
  B=224, 320, 448 with cap 640 and the default window.
- If B=320 is one batch and p95 <= 350 ms, Phase 4 is a cap change only.
- If B=320 is one batch and p95 > 350 ms, report the model floor.
