---
type: CODING
time: 2026-11-19T20:35:00+05:30
summary: Bound the stream queue and stop work for slow readers. Add a slow-reader probe.
paths: Code/batch/server.py; Code/probes/check_stream_backpressure.py; .stageset/facts.md
related: IDEA-0005; FACT-0101
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Stream queue is bounded to 64 chunks.
- A full queue stops the job and counts a slow client.
- The generator exits when the job ends and the queue is empty.

## Outcomes

- The slow-reader probe passes. `slow_clients` is 29, worker queue depth is 0.
- Regular server probe still passes.

## Open items

- Long-frame capacity and HTTP load probe.
