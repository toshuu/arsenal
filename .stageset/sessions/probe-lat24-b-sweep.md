---
type: PROBE
time: 2026-11-22T20:21:52+00:00
summary: Sweep B for the 24-frame latency tier and find the 100/200/350 ms gates.
paths: .stageset/runs/20261122-202152-RUN.md
related: FACT-0162; IDEA-0008; 20261122-235919-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Probe

- Real WS burst gate, latency mode, 24 first frames, default and conditioned v1
  voices. 0 errors on all rows after the `first_only` integrity fix.
- Default voice: 100 ms not met; 200 ms B=48; 350 ms B=96.
- Conditioned v1: 100 ms not met; 200 ms and 350 ms B=64.

## Result

- PASS. See `.stageset/runs/20261122-202152-RUN.md` and FACT-0162.

## Notes

- Not committed.
