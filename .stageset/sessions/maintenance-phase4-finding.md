---
type: MAINTENANCE
time: 2026-11-22T19:33:57+05:30
summary: Record the Phase 4 cap probe result. A cap raise does not stop the early tiny batch.
paths: .stageset/facts.md; .stageset/runs/20261122-192327-RUN.md; Ideas/IDEA-0008-natural-live-call-streaming.md
related: IDEA-0008; FACT-0152; SSLD-025; 20261122-192327-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Phase 4 is a formation problem, not a `BatchedStream` resize problem.
- The next probe must hold the window at the Phase 2 default and vary the quiet
  grace and hard cap for `call_first`.

## Outcomes

- Added FACT-0152 from `20261122-192327-RUN`.
- The cap of 640 did not prevent a 2-4 row early batch at `window=5`.

## Follow-up

- Write a formation probe for `sentence` and `utterance` at cap 640.
- Test the default window (150 ms) and the quiet grace options.
- Pick the policy that gives one batch at B=320 and B=448.
