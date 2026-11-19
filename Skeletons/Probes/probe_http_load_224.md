<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0005
@stageset status: READY
@stageset priority: P0
@stageset spec_revision: 2
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/ideation-burst-224-handoff.md
@stageset last_updated_in: .stageset/sessions/ideation-burst-224-handoff.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: fix and recheck 224-client burst

## Goal

Reach p95 first chunk <= 350 ms at 224 concurrent HTTP clients on one T4. Keep RTF below 1.0 and 0 errors.

## Probe instructions

- Run from the repository root.
- Use `ARSENAL_LOAD_LIMITS=256` for 224 clients. Use default client limits for 32 clients.
- Use `ARSENAL_MAX_BATCH=224`, `ARSENAL_MAX_ROWS=224`, `ARSENAL_BATCH_TARGET=224`.
- Keep the priority queue and the 64-chunk stream bound.
- Add a per-request first-chunk metric. Do not use the current all-chunk metric as the gate.
- Do not change probe client limits between compared runs.
- Do not add per-row RoPE or shared voice KV without owner permission.
- Write only to `Code/probes/out/` and StageSet files.

## Expected observations

- The JSON has `first_p50_ms`, `first_p95_ms`, `errors`, and burst RTF values.
- `first_p95_ms` is <= 350.
- `errors` is 0.
- RTF is below 1.0 for every burst.

## Safety boundary

The probe must not change model weights. It must not send data outside the machine. It must not claim a pass without the saved JSON.

## Assumptions

ASSUMPTION: A-30 - A 224-client burst needs a row-based admission rule, not only a wider time window. [UNVERIFIED]
ASSUMPTION: A-31 - The fixed probe client limit is required for comparable numbers. [VERIFIED]

## Checks

### CHECK-LOAD-224-01 - 224-client gate

- Command: `ARSENAL_LOAD_LIMITS=256 ARSENAL_MAX_BATCH=224 ARSENAL_MAX_ROWS=224 ARSENAL_BATCH_TARGET=224 ARSENAL_LOAD_BURSTS=2 ARSENAL_LOAD_PER_BURST=224 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 448, "p95": <= 350}`
- Pass condition: saved JSON has p95 <= 350, 0 errors, RTF < 1.0.
- Fail condition: p95 above 350, any non-200 response, or RTF at or above 1.0.

### CHECK-LOAD-224-02 - 32-client gate not regressed

- Command: `env -u ARSENAL_MAX_BATCH ARSENAL_LOAD_BURSTS=5 ARSENAL_LOAD_PER_BURST=32 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 160, "p95": <= 350}`
- Pass condition: p95 <= 350 and 0 errors.
- Fail condition: p95 above 350 or any non-200 response.

## References

- `Ideas/IDEA-0005-long-text-and-production-readiness.md`, sections 14 to 16.
- `FACT-0107`, `FACT-0108`.
- `Code/probes/probe_http_load.py`.
- `probes/out/probe_http_load_b224_w40_final.json`.
