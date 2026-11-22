---
type: CODING
time: 2026-11-22T15:08:20+05:30
summary: Verify real WS sentence and utterance modes and fix cap-hit/send bugs.
paths: Code/batch/server.py; Code/probes/probe_ws_quality_modes.py; Code/probes/out/ws_quality/; Ideas/IDEA-0008-natural-live-call-streaming.md; .stageset/runs/20261122-150820-RUN.md
related: IDEA-0008; SSLD-023; 20261122-150820-RUN; 20261122-151455-RUN; FACT-0149; FACT-0150
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Test real `/ws/tts` with `sentence` and `utterance`.
- Fix bugs found in probe before recording pass.

## Outcomes

- Fixed `logging` import, cap_hit attribution for quality mode streams, and WS send deadlock (async sender task).
- Real T4 result: `sentence` 247.42 ms, 18.16 s, 3 chunks, 0 cap_hit; `utterance` 180.57 ms, 17.28 s, 1 chunk, 0 cap_hit.
- WAVs: `Code/probes/out/ws_quality/sentence.wav`, `utterance.wav`.
- 20x warm A/B: `sentence` p50 179.11 ms p95 186.13 ms; `utterance` p50 178.79 ms p95 182.26 ms. No meaningful difference (FACT-0150).

## Follow-up

- Run B-ramp on server path with `sentence` default.
- Test mixed short+long first-byte; add first-chunk bucketing if needed.
