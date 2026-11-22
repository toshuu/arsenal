---
type: CODING
time: 2026-11-22T14:34:43+05:30
summary: Record the SSLD-022 listening gate and make sentence the default quality mode.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; Code/probes/out/natural_stream/; .stageset/facts.md
related: IDEA-0008; SSLD-022; FACT-0147; FACT-0148; 20261122-142726-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- The `utterance` and `sentence` WAVs match in quality by ear.
- Use `sentence` as the default quality mode.
- Keep `utterance` as the low-load fallback.
- Keep `latency` for extreme load only.
- Do not treat this as proof of the high-B gate. Phase 2 must measure B=224 and
  B=448.

## Outcomes

- Added FACT-0148.
- Updated IDEA-0008 with the listening gate, the mode table, and the Phase 1
  choice.

## Follow-up

- Write the server mode plan with `sentence` as the default.
- Add first-chunk size buckets for mixed text.
- Run Phase 2 at B=224 and B=448.
