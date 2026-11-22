---
type: CODING
time: 2026-11-22T14:47:10+05:30
summary: Implement WS quality modes with sentence as the default and raw frames.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; Skeletons/Code/batch/server.py; LivingDocs/SSLD-023-server-quality-modes.md; Code/batch/server.py; Code/probes/check_server_modes.py; Code/probes/check_call_ws.py
related: IDEA-0008; SSLD-023; 20261122-144709-RUN; 20261122-144709-RUN-02; 20261122-144710-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- WS `start` accepts `stream_mode` or `mode`. Default is `ARSENAL_CALL_STREAM_MODE`
  or `sentence`.
- `sentence` uses no first-token cut, 224 frames, and 50-token chunks.
- `utterance` uses no first-token cut, 512 frames, and one whole-text job.
- `latency` keeps the legacy 16-token cut and pause compression.
- Quality modes send raw frames. No pause compressor.
- HTTP `/tts/stream?mode=call` is unchanged.

## Outcomes

- Added mode helpers and a CPU check.
- Routed each job's `stream_mode` to the engine. Added cached mode streams.
- Wired mode chunking and frame caps into `/ws/tts`.
- Fixed two pre-existing check failures: missing `re` import and fake-engine
  `_stream_for` guard.
- Updated `check_call_ws.py` to read the `utterance_done` event before cancel and
  flush.
- All three checks PASS. See the linked run reports.

## Follow-up

- Run a real-model WS WAV check for `sentence` and `utterance`.
- Run the B ramp with short first chunks.
- Check mixed text with first-chunk buckets.
