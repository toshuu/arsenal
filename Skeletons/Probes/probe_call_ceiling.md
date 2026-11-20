<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0007
@stageset status: READY
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 0
@stageset planned_in: .stageset/sessions/plan-call-mode.md
@stageset last_updated_in: .stageset/sessions/plan-call-mode.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: first-chunk B ceiling

## Goal

Answer one question before any code: if the first chunk uses only 24, 32, or 48
frames, how high does B go at a first-chunk p95 of 350, 200, and 100 ms on one T4?

This probe uses the current server and the in-container `/debug/selfprobe` path. It
does not add WebSocket or job classes. It measures the model and batch ceiling.

## Probe instructions

- Run in-container on the Modal T4. Use no public proxy.
- Use one conditioned profile (`ARSENAL_LOAD_SINGLE_PROFILE=v1`) or the reference
  voice. Keep the same voice for the whole probe.
- Set `ARSENAL_MAX_QUEUE`, `ARSENAL_MAX_ROWS`, `ARSENAL_MAX_BATCH`, and
  `ARSENAL_BATCH_TARGET` to at least the top B in the ramp.
- Set `ARSENAL_DEBUG=1`.
- Use burst arrivals over 2 bursts. Warm the pool with one B=8 burst first.
- Ramp B = 224, 320, 448, 512, 640, 768, 896, 1024. Stop at the first failure.
  A failure is p95 above the gate for the current `max_frames`, or any error, or OOM.
- Sweep `max_frames` = 24, 32, 48.
- Sweep `window` = 0, 5, 10, 25 ms.
- Record peak VRAM after each burst.
- Write only to `probes/out/` and StageSet files.
- Stop the app after: `modal app stop arsenal-tts-t4 -y`.

## Commands

```text
modal deploy Code/deploy/modal_app.py
curl "$URL/health"
# warm
curl "$URL/debug/selfprobe?b=8&bursts=1&window=10&target=<B>&max_frames=32&empty_cache=1"
# ramp (one call per cell)
curl "$URL/debug/selfprobe?b=<B>&bursts=2&window=<W>&target=<B>&max_frames=<MF>&empty_cache=1"
curl "$URL/debug/vram"
modal app stop arsenal-tts-t4 -y
```

## Expected observations

- A JSON object per cell with `client.p50_ms`, `client.p95_ms`, `client.errors`,
  and `server` metrics.
- A table: `max_frames | window | B | first p50 | first p95 | peak VRAM MB | errors`.
- The max B that passes each gate: 350, 200, 100 ms.
- Fact rows for the measured ceiling. The estimate table in IDEA-0007 is replaced
  by measured values.

## Safety boundary

- Do not change model weights.
- Do not send data outside the machine.
- Do not edit project code in this probe.
- Do not claim a pass without saved JSON.
- Stop the GPU after the probe.

## Assumptions

ASSUMPTION: A-45 - The selfprobe first byte equals the call-mode first chunk when
`max_frames` is small. [UNVERIFIED] It is a normal-path proxy, not the WS path.
ASSUMPTION: A-46 - A T4 with 8 CPU can run the ASGI selfprobe without the host
CPU limit of the 4-vCPU Kaggle box. [VERIFIED] FACT-0123 shows low handler offsets
in-container.

## Checks

### CHECK-CALL-CEILING-01 - 350 ms gate

- Command: the ramp above with `window=10`, `max_frames=32`.
- Predicted output: `{"client": {"p95_ms": <= 350, "errors": 0}}`
- Pass condition: a saved JSON shows p95 <= 350 ms and 0 errors at the reported max B.
- Fail condition: p95 above 350 ms with 0 errors at a lower B than 224, or any error.

### CHECK-CALL-CEILING-02 - 200 ms gate

- Command: the ramp above with the best window and `max_frames` from CHECK-CALL-CEILING-01.
- Predicted output: `{"client": {"p95_ms": <= 200, "errors": 0}}`
- Pass condition: a saved JSON shows p95 <= 200 ms and 0 errors at the reported max B.
- Fail condition: no B >= 128 passes 200 ms.

### CHECK-CALL-CEILING-03 - 100 ms gate

- Command: the ramp above with the best window and `max_frames` from CHECK-CALL-CEILING-02.
- Predicted output: `{"client": {"p95_ms": <= 100, "errors": 0}}`
- Pass condition: a saved JSON shows p95 <= 100 ms and 0 errors at the reported max B.
- Fail condition: no B >= 64 passes 100 ms. Report the floor.

## References

- `Ideas/IDEA-0007-dual-service-call-mode.md`
- `Code/batch/server.py` (`/debug/selfprobe`, `/debug/vram`)
- `Code/deploy/modal_app.py`
- `.stageset/runs/20261120-142010-RUN.md`
