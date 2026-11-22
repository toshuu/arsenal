---
type: CODING
time: 2026-11-22T19:53:19+00:00
summary: Latency WS now uses sentence-mode chunks for all text after the first frame-budget chunk.
paths: Code/batch/server.py; Code/batch/call_chunker.py
related: IDEA-0008; FACT-0161; 20261122-235919-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Change

- In latency mode, the first chunk keeps the frame budget (`CALL_FIRST`,
  latency stream, pause compression, user cap).
- The remaining text is split with `chunk_stream._text_chunks` and submitted as
  `sentence` chunks (sentence stream, sentence quality cap 224, no pause
  compression). Each continuation carries `chunk_mode="sentence"`.
- `call_chunker.py` adds `first_chunk_words` for the first-chunk word count.
- Owner decision: the optimal first chunk is 24 frames (first_frames), then the
  rest is sentence based. Recorded as FACT-0161.

## Result

- Cap 24: chunk 0 latency 16 frames 1.28 s; chunks 1-2 sentence 33 and 41
  frames, 2.64 s and 3.28 s. All EOS, no cap hit.
- Cap 56: chunk 0 latency 30 frames 2.4 s; chunks 1-2 sentence 36 and 25
  frames, 2.88 s and 2.0 s. All EOS, no cap hit.

## Notes

- Sentence chunker capitalizes the first letter of continuation chunks. Text
  integrity passes after normalization.
