---
type: CODING
time: 2026-11-19T20:52:00+05:30
summary: Fix HTTP load latency with chunk scheduling, a wider batch window, and per-row voice batching.
paths: Code/batch/server.py; Code/batch/batched_stream.py; Code/probes/probe_http_load.py; Code/probes/check_stream_backpressure.py; docs/voice-profiles.md; Code/batch/VOICE_PROFILES.md; Ideas/IDEA-0005-long-text-and-production-readiness.md; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0102; FACT-0103; FACT-0104
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Submit one text chunk per job. First chunks batch before continuations.
- Use a 100 ms batch window. An 8 ms window missed arriving requests.
- Use per-row voice tensors in the normal path for mixed profile ids.
- Keep the conditioned fast path for one profile id with equal token lengths.
- Do not add carried state. Objective join checks pass. Listening is pending.

## Outcomes

- HTTP load: 160 requests, p50 173.68 ms, p95 226.66 ms, 0 errors, RTF < 0.03.
- B=224 with max_frames=192 fits with 1.95 GiB free.
- All earlier probes pass.

## Open items

- Owner listening gate for chunk joins.
- L4 and Modal stay out of scope.
