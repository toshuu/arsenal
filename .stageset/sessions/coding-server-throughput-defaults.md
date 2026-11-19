---
type: CODING
time: 2026-11-19T20:10:00+05:30
summary: Match server defaults to the final T4 point. Add prewarm, row cap, and 413 for over-limit frames.
paths: Code/batch/server.py; Code/probes/check_server.py; Code/batch/VOICE_PROFILES.md; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0056; FACT-0064; FACT-0087; FACT-0096
commit: fcffdb4
remote: -
branch: -
---

# Session notes

## Decisions

- Server defaults: max batch 192, max rows 224, max queue 256, max frames 192.
- Boot runs prewarm B=192, 1 frame.
- The worker caps rows, not only jobs.
- An over-limit `max_frames` returns 413 before submit.
- Use the final T4 figures (B=224 cap), not the old B=128 target.

## Outcomes

- Boot to readiness is 7 s. Prewarm is 350.9 ms.
- Real TTS returns 200.
- Fake probe passes 13 checks.
- Validate passes.

## Open items

- Streaming response and TTFA metrics remain.
- Chunk joins need a listening and objective test.
