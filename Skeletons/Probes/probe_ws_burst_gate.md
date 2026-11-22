<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 5
@stageset implemented_revision: 5
@stageset planned_in: .stageset/sessions/maintenance-ssld-033-spec5.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-033-formation.md
@stageset implemented_in: .stageset/sessions/coding-ssld-033-formation.md
@stageset blocker_ref: -
@stageset resolution_of: 20261123-000000-RUN
-->

# Probe: real WS low-latency gate with confirmed formation

## Goal

Confirm the low-latency WebSocket first-sound gate on the current app revision.
The WebSocket is open before the text is sent. The clock starts at text send
and stops at the first audio byte.

This probe uses the formation settings that already passed in FACT-0139. It
does not change app code.

## Method

- Start one fresh uvicorn server.
- Set `ARSENAL_MAX_ROWS=640`, `ARSENAL_MAX_BATCH=640`,
  `ARSENAL_BATCH_TARGET=640`, and `ARSENAL_MAX_FRAMES=192`.
- Set `ARSENAL_CALL_FIRST_MAX_BATCH=640`,
  `ARSENAL_CALL_FIRST_SUB_BATCH=640`,
  `ARSENAL_CALL_FIRST_MAX_FRAMES=8`, and
  `ARSENAL_CALL_CONT_MAX_FRAMES=192`.
- Set `ARSENAL_CALL_FIRST_QUIET_MS=50`,
  `ARSENAL_CALL_FIRST_HARD_CAP_MS=300`, and
  `ARSENAL_CALL_FIRST_GRACE_MS=20`. Do not set `MIN_EARLY`.
- Keep `ARSENAL_BATCH_WINDOW_MS=150` and prewarm on.
- Run `Code/probes/ws_burst_gate_client.py` with `--mode sentence` and
  `--max-frames 8`, at B=224, 320, and 384.
- Use 2 warmups and 4 measured repetitions. Pre-connect all WS clients.
- Client text: `Hello, can you hear me clearly right now?`
- Save `Code/probes/out/ws_burst_gate/gate.json`.
- Write `probe_sha256` and `client_sha256` into `gate.json`.
- Record `call_first_wait_ms` and `batch_wait_ms` from `/metrics` for each run.

## Decision rule

- Main gate: B=320 has 0 errors and `p95_of_p95` <= 350 ms.
- Report B=224 and B=384 as the lower and upper data points.
- `max_b_under_350` is the largest tested B under 350 ms.
- This is a latency gate. It is not a listening gate.
- `utterance` is not tested. It forces 512 frames per row and OOMs at B=224.

## Checks

### CHECK-WS-GATE-01 - probe rows

- Command: `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print(len(d['rows']), [r['b'] for r in d['rows']], d['mode'], d['first_frames'])"`
- Predicted output: `3 [224, 320, 384] sentence 8`
- Pass condition: 3 rows in that order, mode sentence, first_frames 8.
- Fail condition: any other output.

### CHECK-WS-GATE-02 - gate

- Command: `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print(d['gate_320'], d['max_b_under_350'], all(r['errors']==0 for r in d['rows']))"`
- Predicted output: `True 320 True`.
- Pass condition: gate_320 true, max_b at least 320, every row has 0 errors.
- Fail condition: gate false, max_b below 320, or any error.

### CHECK-WS-GATE-03 - provenance

- Command: `python -c "import json,hashlib,pathlib; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); p=pathlib.Path('Code/probes/probe_ws_burst_gate.py'); c=pathlib.Path('Code/probes/ws_burst_gate_client.py'); print(d['probe_sha256']==hashlib.sha256(p.read_bytes()).hexdigest(), d['client_sha256']==hashlib.sha256(c.read_bytes()).hexdigest(), all(r.get('call_first_wait_ms') is not None for r in d['rows']))"`
- Predicted output: `True True True`
- Pass condition: both SHA values match and every row has formation wait.
- Fail condition: any mismatch or missing metric.

## References

- `Code/probes/ws_burst_gate_client.py`
- `Code/batch/server.py`
- `.stageset/runs/20261121-120307-RUN.md`
- `.stageset/runs/20261122-195007-RUN.md`
- `.stageset/runs/20261122-235500-RUN.md`
- `LivingDocs/SSLD-033-formation-modes.md`
