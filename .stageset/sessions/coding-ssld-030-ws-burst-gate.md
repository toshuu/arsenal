---
type: CODING
time: 2026-11-22T15:48:52+00:00
summary: Run the real WebSocket burst gate at the default call config.
paths: Code/probes/probe_ws_burst_gate.py; Code/probes/out/ws_burst_gate/gate.json; .stageset/runs/20261122-210000-RUN.md; Skeletons/Probes/probe_ws_burst_gate.md
related: IDEA-0008; SSLD-030; FACT-0154; 20261122-210000-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Measure the real WS path with `sentence` at B=224 and B=320.
- Do not change app code in this step.

## Outcomes

- Gate table and decision are in `20261122-210000-RUN`.

## Follow-up

- Planner reads the run report. If B=224 passes, lock it. If not, inspect the client and server phase gaps.
