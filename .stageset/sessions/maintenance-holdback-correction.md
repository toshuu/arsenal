---
type: MAINTENANCE
time: 2026-11-22T20:40:00+00:00
summary: Correct the holdback claim and add a holdback env knob for the latency compressor.
paths: Code/batch/server.py; .stageset/facts.md
related: FACT-0162; FACT-0163; 20261122-202152-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Change

- Added `ARSENAL_CALL_HOLDBACK_MS` to control the latency pause-compressor
  holdback. Default stays 50 ms.
- Measured holdback 50 vs 8 ms at B=48 conditioned. The holdback adds about
  16 ms to p50, not the full gap against FACT-0159.
- Corrected the earlier claim that the 50 ms holdback explained the 100 ms gate
  miss. Recorded as FACT-0163.
- Found that holdback 0 is invalid because Python `buf[:-0]` is empty.

## Notes

- Not committed.
