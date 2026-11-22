---
type: MAINTENANCE
time: 2026-11-22T19:56:35+00:00
summary: Record owner decision that the optimal latency design is 24 first frames then sentence-based chunks.
paths: .stageset/facts.md
related: IDEA-0008; FACT-0161; coding-latency-then-sentence
commit: -
remote: -
branch: -
---

# Session notes

## Decision

- The optimal first chunk is 24 frames (first_frames). The remaining text is
  synthesized with sentence-based chunks and the sentence quality cap.
- The latency WS path now implements this split: first chunk on the latency
  stream, later chunks in sentence mode.
- Recorded as FACT-0161 in `.stageset/facts.md`.
