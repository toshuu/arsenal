---
type: CODING
time: 2026-11-20T23:00:00+05:30
summary: Wire call-mode job classes and the call WebSocket into the server. Fake-engine checks pass.
paths: Code/batch/server.py; Code/probes/check_call_ws.py; Code/probes/check_server.py; LivingDocs/SSLD-020-call-mode-server-wiring.md
related: IDEA-0007; SSLD-020; FACT-0128; 20261120-225605-RUN; 20261120-225605-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Work done

- Ran SSLD-020. Edited `Code/batch/server.py` for class queues, the call job classes, call metrics, and `/ws/tts`.
- Added `Code/probes/check_call_ws.py`.
- Fixed the fake engines in `Code/probes/check_server.py` to accept `on_stage`. The server always passed it.

## Evidence

- CHECK-CALL-WS-01 PASS: `.stageset/runs/20261120-225605-RUN.md`.
- CHECK-SERVER-01 PASS: `.stageset/runs/20261120-225605-RUN-02.md`.

## Skeleton state

- `Skeletons/Code/batch/server.py` stays at implemented revision 8. Revision 10 is not complete: the debug routes and the real-model checks are missing.
