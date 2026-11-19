<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0005
@stageset status: READY
@stageset priority: P0
@stageset spec_revision: 3
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/ideation-burst-224-handoff.md
@stageset last_updated_in: .stageset/sessions/coding-b224-ramp.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: fix and recheck 224-client burst

## Goal

Reach p95 first chunk <= 350 ms at 224 concurrent HTTP clients on one T4. Keep RTF below 1.0 and 0 errors.

Owner dislike point: `2026-11-19T20:50:20+05:30`. Start from the pre-dislike baseline. Do not treat post-point scheduler changes as accepted without revalidation. See IDEA-0005 section 17.

## Probe instructions

- Run from the repository root.
- Use `ARSENAL_LOAD_LIMITS=256` for 224 clients. Use default client limits for 32 clients.
- Use `ARSENAL_MAX_BATCH=224`, `ARSENAL_MAX_ROWS=224`, `ARSENAL_BATCH_TARGET=224`.
- Keep the priority queue and the 64-chunk stream bound.
- The server has `request_first_chunk_ms`. Use it with the client p95.
- The probe reads `ARSENAL_LOAD_LIMITS`, uses one async client, a start barrier, and a warm pool.
- Use `ARSENAL_LOAD_SINGLE_PROFILE=v1` to compare with the pre-dislike conditioned baseline.
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

- Command: `ARSENAL_LOAD_LIMITS=256 ARSENAL_LOAD_SINGLE_PROFILE=v1 ARSENAL_MAX_BATCH=224 ARSENAL_MAX_ROWS=224 ARSENAL_BATCH_TARGET=224 ARSENAL_BATCH_WINDOW_MS=700 ARSENAL_LOAD_BURSTS=2 ARSENAL_LOAD_PER_BURST=224 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 448, "p95": <= 350}`
- Pass condition: saved JSON has p95 <= 350, 0 errors, RTF < 1.0.
- Fail condition: p95 above 350, any non-200 response, or RTF at or above 1.0.

### CHECK-LOAD-224-02 - 32-client gate not regressed

- Command: `env -u ARSENAL_MAX_BATCH ARSENAL_LOAD_BURSTS=5 ARSENAL_LOAD_PER_BURST=32 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 160, "p95": <= 350}`
- Pass condition: p95 <= 350 and 0 errors.
- Fail condition: p95 above 350 or any non-200 response.

## Current evidence (2026-11-20)

- Direct B=224 model first emit: p95 97.7 ms (FACT-0111).
- 32-client HTTP gate: PASS, client p95 340.6 ms, server p95 294.0 ms (FACT-0110).
- Steps 1,2,4 ramp (separate client/server cores, uvloop+httptools, single profile, 2 bursts): max B pass = **37** at window 150 ms (server 241.0 ms, client 315.0 ms, queue 148.7 ms, 0 err). B=38 failed (FACT-0115, `20261120-013315-RUN`).
- B=224 window sweep: best server 1542.1 ms at window 10 ms; client 5627.9 ms; 0 err but FAIL (FACT-0116, `20261120-013315-RUN-02`).
- Gap: head-of-line/ingress on 4-vCPU host. Step 3 (continuous batching) not implemented; plan and approval required.

## References

- `Ideas/IDEA-0005-long-text-and-production-readiness.md`, sections 14 to 19.
- `FACT-0110`, `FACT-0111`, `FACT-0112`, `FACT-0113`, `FACT-0115`, `FACT-0116`.
- `Code/probes/probe_http_load.py`, `Code/probes/ramp_b.py`.
- `probes/out/sweep_b32_s14.json`, `probes/out/sweep_b36_s14.json`, `probes/out/ramp_exact_s14.json`, `probes/out/sweep_b224_s4.json`.
