---
type: IDEATION
time: 2026-11-22T15:22:00+05:30
summary: Plan Phase 2 B-ramp for sentence and utterance on server path.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; LivingDocs/SSLD-024-phase2-b-ramp.md
related: IDEA-0008; FACT-0147; FACT-0148; FACT-0149; FACT-0150
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Double-assure: test `sentence` and `utterance`.
- Use `/debug/callramp` with `stream_mode`, `first_only=1`, short text.
- Gates: 350ms (224-448), 200ms (96-224), 100ms (32-96).
- Record max B, first-byte p95, batch sizes, VRAM, errors.
- Quality mode stays raw; no pause compression.

## Outcomes

- Added SSLD-024.

## Follow-up

- Run SSLD-024, record FACTs, update IDEA-0008.
