---
type: CODING
time: 2026-11-22T19:45:00+00:00
summary: Split latency text by frame budget so cap-hit no longer cuts words.
paths: Code/batch/server.py; Code/batch/call_chunker.py
related: IDEA-0008; 20261122-235919-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Problem

- With cap 24, the server sent the full text as one job. The model stopped at
  the cap mid-word. Audio cut off and sounded wrong.
- An earlier attempt divided max_frames by 2 in the WS handler. That was wrong:
  one flow step produces one audio frame. It was reverted.

## Fix

- `call_chunker.py` adds `split_by_frame_budget(text, audio_frames)`. It groups
  words so each chunk fits the cap. The estimate is 7 audio frames per word.
- The WS handler uses this splitter for latency mode. The page still sends the
  full text; the server splits by frame budget.
- `server.py` keeps max_frames in flow steps. No unit conversion. The frame cap
  is the ceiling, and each chunk reaches EOS before it.

## Result

- Cap 24: 7 chunks, all EOS, no cap hit, no cut words. 0.88-1.76 s per chunk.
- Cap 56: 3 chunks, all EOS, no cap hit, no cut words. 1.68-3.42 s per chunk.

## Notes

- Not committed.
