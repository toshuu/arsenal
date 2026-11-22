---
type: MAINTENANCE
time: 2026-11-22T16:19:46+00:00
summary: Review the SSLD-031 block. Replace the shared client with a dedicated gate client.
paths: LivingDocs/SSLD-032-gate-client.md; Skeletons/Probes/probe_ws_burst_gate.md; Code/probes/call_load_client.py
related: IDEA-0008; SSLD-031; SSLD-032; 20261122-210000-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Block

SSLD-031 stopped at T004.

- The HEAD `call_load_client.py` calls `drain()` before each repetition.
- `drain()` waits for `active_call_sessions == 0`.
- All B clients stay connected. So `active_call_sessions` stays at B.
- `drain()` waits the full 120 s timeout before each repetition.
- Two B values need more than the 2400 s probe timeout.

## Second defect

The HEAD client sends `cancel` after each `first_only` run.

- The server sets `state["cancelled"] = True` on `cancel`.
- The server resets it only on `start`.
- The next `text` on the same WebSocket sees `cancelled` and sends no audio.

So the HEAD client cannot reuse one connection for several measured runs
without a new `start`.

## Decision

Create a dedicated client for the gate. Do not edit the shared client again.

The dedicated client:

1. Opens B WebSockets once and sends `start` once.
2. Runs 2 warmups and 4 measured repetitions on the same sockets.
3. Does not send `cancel` between repetitions.
4. Does not call `drain()`.
5. Measures text send to first audio byte.
6. Reports warm-only p50 and p95.
7. Writes one JSON file.

The probe will call this client and bind its SHA-256.

## Non-goals

- No app code change.
- No collector tuning.
- No commit.
