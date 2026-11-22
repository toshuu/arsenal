---
type: CODING
time: 2026-11-22T16:37:59+00:00
summary: Add the dedicated gate client and run the corrected WS gate.
paths: Code/probes/ws_burst_gate_client.py; Code/probes/probe_ws_burst_gate.py; Code/probes/out/ws_burst_gate/gate.json; .stageset/runs/20261122-230000-RUN.md; Skeletons/Probes/probe_ws_burst_gate.md
related: IDEA-0008; SSLD-031; SSLD-032; 20261122-230000-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use a dedicated client with no `cancel` and no `drain`.
- Bind the output with SHA-256.

## Outcomes

- The corrected gate table is in `20261122-230000-RUN`.

## Follow-up

- Planner locks B=224 if the gate passes. Inspect the phase gap if it fails.
