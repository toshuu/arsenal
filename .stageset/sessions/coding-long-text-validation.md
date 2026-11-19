---
type: CODING
time: 2026-11-19T20:34:00+05:30
summary: Add probes for long-text edges, long text over HTTP with a profile, and chunk joins.
paths: Code/probes/check_long_text_edges.py; Code/probes/check_long_text_http.py; Code/probes/check_chunk_joins.py; .stageset/facts.md
related: IDEA-0005; FACT-0098; FACT-0099; FACT-0100
commit: 3ab3fee
remote: -
branch: -
---

# Session notes

## Decisions

- Keep independent chunks. Do not add carried state unless the listening gate fails.
- Chunk join probes save WAVs for the owner.
- Edge coverage uses exact word order, not only a word set.

## Outcomes

- Six hard text shapes pass coverage and frame estimates.
- Long text over HTTP with a profile passes. First-chunk p95 is 110.4 ms.
- Chunk joins have no objective click or RMS drop.

## Open items

- Owner listening gate for `/kaggle/working/chunk_joins_normal.wav` and `chunk_joins_profile.wav`.
- Backpressure, long-frame capacity, and HTTP load probe.
