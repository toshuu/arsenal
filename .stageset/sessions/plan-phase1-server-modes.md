---
type: IDEATION
time: 2026-11-22T14:40:23+05:30
summary: Plan short Phase 1 server modes with sentence as the default quality mode.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; Skeletons/Code/batch/server.py; LivingDocs/SSLD-023-server-quality-modes.md
related: IDEA-0008; FACT-0147; FACT-0148
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Add `sentence`, `utterance`, and `latency` to the WS call path.
- Use `sentence` as the default. `utterance` is the low-load fallback.
- Quality modes must not use pause compression or fixed join.
- Use the selected mode's BatchedStream settings. Do not let the legacy
  16-token first cap re-cut a quality chunk.
- Keep HTTP `/tts/stream?mode=call` unchanged in this phase.
- Keep docs short. The skeleton and SSLD must fit one screen each.

## Outcomes

- Raised `server` skeleton spec to revision 11.
- Added SSLD-023 for the Phase 1 implementation.

## Follow-up

- Run SSLD-023.
- Record a run report for each check.
- Then run the server quality and B probes.
