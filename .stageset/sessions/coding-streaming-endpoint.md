---
type: CODING
time: 2026-11-19T20:15:00+05:30
summary: Add first-chunk PCM streaming endpoint and latency metrics.
paths: Code/batch/server.py; Code/probes/check_server.py; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0097
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- `/tts/stream` returns raw 16-bit PCM (`audio/L16`) as chunks arrive.
- The worker relays each emitted frame to the job callback.
- Stream requests copy each frame to CPU PCM in the worker. Buffered requests do not.
- Metrics keep the last 1000 samples for queue, first chunk, and total time.
- The first chunk is sent before generation ends.

## Outcomes

- Real engine: TTFB 82.9 ms, total 974.7 ms, 96 frames.
- Full buffered call: 896.6 ms.
- First-chunk metric p50: 80.74 ms.
- Fake probe passes 15 checks.
- Validate passes.

## Open items

- End-to-end load probe with mixed profiles and lengths.
- A slow-client queue bound for long streams.
- Chunk join listening test.
