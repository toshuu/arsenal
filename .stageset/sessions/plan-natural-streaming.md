---
type: IDEATION
time: 2026-11-22T14:10:20+05:30
summary: Define the natural live-call streaming strategy and Phase 0 measurement.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; Skeletons/Probes/probe_natural_stream.md; LivingDocs/SSLD-022-natural-live-call-streaming.md
related: IDEA-0007; IDEA-0008
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep frame streaming, per-row EOS, and compact row removal.
- Remove the 16-token first-chunk cut and pause compression from quality mode.
- Use three text policies: utterance, sentence, and latency.
- Measure before code. Phase 0 compares the three policies.
- Do not claim 100 ms p95 at B=224.

## Outcomes

- Added IDEA-0008 with the strategy and target gates.
- Added the natural stream probe skeleton.
- Added SSLD-022 for Phase 0 measurement.

## Follow-up

- Run SSLD-022 on the T4. Read the three JSON results. Then write the server mode plan.
