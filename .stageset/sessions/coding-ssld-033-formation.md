---
type: CODING
time: 2026-11-22T17:11:56+00:00
summary: Add max_frames to the gate client and restore confirmed formation in the probe.
paths: Code/probes/ws_burst_gate_client.py; Code/probes/probe_ws_burst_gate.py
related: IDEA-0008; SSLD-033; 20261123-000000-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Change

- The client sends `max_frames` in the text message.
- The probe uses cap 640, target 640, mf8, quiet 50, hard cap 300, grace 20.
- The probe tests `sentence` at B=224, 320, and 384.

## Result

See `.stageset/runs/20261123-000000-RUN.md`.
