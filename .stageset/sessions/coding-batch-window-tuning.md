---
type: CODING
time: 2026-11-19T21:13:00+05:30
summary: Test B=224 with a 40 ms batch window. Add first-chunk priority and set the default window to 180 ms.
paths: Code/batch/server.py; Code/probes/probe_http_load.py; docs/voice-profiles.md; Code/batch/VOICE_PROFILES.md; Ideas/IDEA-0005-long-text-and-production-readiness.md; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0105; FACT-0106
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep the 40 ms result as a negative fact. Do not hide it.
- Use a priority queue. First chunks run before continuations.
- Set the default batch window to 180 ms.
- Do not claim the 224-client burst gate passes.

## Outcomes

- B=224, 40 ms: p50 2511.55 ms, p95 6047.72 ms, 0 errors. Queue p50 733.84 ms.
- B=32, 180 ms: p50 254.96 ms, p95 321.32 ms, 0 errors.
- All standard probes pass.

## Open items

- 224-client bursts need a better admission or window rule.
