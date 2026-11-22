<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/maintenance-phase4-formation-review.md
@stageset last_updated_in: .stageset/sessions/maintenance-phase4-formation-review.md
@stageset implemented_in: .stageset/sessions/coding-phase4-confirm.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Phase 4 real-server confirmation

## Goal

Confirm the Phase 4 formation result on a separate-process uvicorn server. The
in-process p95 is not a gate. Use the default window. Raise the cap to 640.

## Method

- Start one local uvicorn server with `ARSENAL_DEBUG=1`.
- Set `ARSENAL_MAX_BATCH`, `ARSENAL_MAX_ROWS`, `ARSENAL_CALL_FIRST_MAX_BATCH`,
  and `ARSENAL_CALL_FIRST_SUB_BATCH` to 640.
- Do not set `ARSENAL_BATCH_WINDOW_MS`. Do not pass the `window` query value.
  The server uses its default of 150 ms.
- Do not set the quiet grace or the hard cap. Both stay at 0.
- Use `sentence` and `utterance`.
- Use B = 224, 320, 448.
- Use 6 calls per cell. Call 0 and call 1 are cold. Call 2 to 5 are warm.
- Record `batch_sizes`, p95, p50, errors, and peak VRAM.
- Use the same short text for every call.

## Output

- One JSON file at `Code/probes/out/phase4_confirm/confirm.json`.
- 36 rows. Each row has `mode`, `b`, `call`, `warm`, `p50`, `p95`, `errors`,
  `batch_sizes`, `vram_after`.

## Decision rule

- If every warm B=320 row is one batch and the worst warm p95 is less than or
  equal to 350 ms, Phase 4 is a cap change only.
- If every warm B=320 row is one batch and the worst warm p95 is greater than
  350 ms, report the model floor. Do not add a formation policy.
- If any warm B=320 row splits, the split is a real formation limit. Report the
  split and stop.

## Safety boundary

- Do not change model weights.
- Do not change app code. This probe adds one script and writes
  `Code/probes/out/`.
- Do not send data off the machine.
- Stop the server after the run.

## Assumptions

ASSUMPTION: A-51 - A separate-process uvicorn server with the default window
forms one call_first batch at B=320. [UNVERIFIED]

ASSUMPTION: A-52 - B=448 at `first_max_frames=8` fits one T4. [UNVERIFIED]

## Checks

### CHECK-PHASE4-CONFIRM-01 - probe JSON

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_confirm/confirm.json')); print(len(d['rows']), sorted({r['b'] for r in d['rows']}))"`
- Predicted output: `36 [224, 320, 448]`
- Pass condition: 36 rows and all three B values.
- Fail condition: missing file or a wrong count.

### CHECK-PHASE4-CONFIRM-02 - one batch at B=320

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_confirm/confirm.json')); w=[r for r in d['rows'] if r['b']==320 and r['warm']]; print(all(r['batch_sizes']==[320] for r in w))"`
- Predicted output: `True` or `False`
- Pass condition: the value is `True`. Report the worst warm p95.
- Fail condition: the value is `False`. Report each batch size.

### CHECK-PHASE4-CONFIRM-03 - worst warm p95 at B=320

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_confirm/confirm.json')); w=[r for r in d['rows'] if r['b']==320 and r['warm']]; m={}; [m.setdefault(r['mode'],[]).append(r['p95']) for r in w]; print({k: max(v) for k,v in m.items()})"`
- Predicted output: a dict with `sentence` and `utterance` values
- Pass condition: both values are less than or equal to 350.
- Fail condition: either value is greater than 350. Report the floor.

## References

- `Ideas/IDEA-0008-natural-live-call-streaming.md`
- `.stageset/runs/20261122-193729-RUN.md`
- `.stageset/runs/20261122-152530-RUN.md`
- `Code/probes/probe_phase2_bramp.py`
