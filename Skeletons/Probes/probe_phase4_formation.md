<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/maintenance-phase4-finding.md
@stageset last_updated_in: .stageset/sessions/maintenance-phase4-finding.md
@stageset implemented_in: .stageset/sessions/coding-phase4-formation.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Phase 4 formation policy

## Goal

Find one `call_first` formation policy that keeps B=320 and B=448 in one batch
under 350 ms. The cap is not the cause. A short window lets a small early batch
start before the rest arrive.

## Method

- Use one in-process ASGI server. This lets the probe change env between cells.
- Set the cap to 640. Set the queue to 4096.
- Use `sentence` and `utterance`.
- Use B = 224, 320, 448.
- Use 3 calls per cell. Call 0 is cold. Call 1 and 2 are warm.
- For each policy, set `ARSENAL_BATCH_WINDOW_MS`,
  `ARSENAL_CALL_FIRST_QUIET_MS`, and `ARSENAL_CALL_FIRST_HARD_CAP_MS`.
- Call `worker.reload_config()` after the env change.
- Call `/debug/callramp` with `first_only=1`, `first_max_frames=8`. Do not pass
  the `window` query value.
- Record `batch_sizes`, p95, errors.

## Policies

| Name | Window ms | Quiet ms | Hard cap ms |
| --- | ---: | ---: | ---: |
| default | 150 | 0 | 0 |
| q2h20 | 150 | 2 | 20 |
| q2h30 | 150 | 2 | 30 |
| q3h40 | 150 | 3 | 40 |

## Decision rule

- A policy wins for one B when all warm rows have `batch_sizes` equal to `[B]`
  and the largest warm p95 is less than or equal to 350 ms.
- Pick the policy that wins at the largest B, then the lowest B. If none wins at
  B=320, report the floor. Do not change app code in this probe.
- The in-process p95 is an estimate. A real uvicorn confirm is a later step.

## Safety boundary

- Do not change model weights.
- Do not change app code. This probe adds one script and writes
  `Code/probes/out/`.
- Do not send data off the machine.
- Stop the server after the run.

## Assumptions

ASSUMPTION: A-49 - `app.state.worker.reload_config()` rereads the window env.
[UNVERIFIED]

ASSUMPTION: A-50 - The in-process batch sizes match the separate-process batch
sizes for the same policy. [UNVERIFIED]

## Checks

### CHECK-PHASE4-FORM-01 - probe JSON

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_formation/formation.json')); print(len(d['rows']), len(d['policies']))"`
- Predicted output: `72 4`
- Pass condition: 72 rows and 4 policies.
- Fail condition: missing file or a wrong count.

### CHECK-PHASE4-FORM-02 - one winning policy

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_formation/formation.json')); w=[r for r in d['rows'] if r['warm'] and r['b']>=320]; print(sorted({(r['policy'], r['b']) for r in w if r['batch_sizes']==[r['b']] and r['p95']<=350}))"`
- Predicted output: one or more `(policy, B)` values, or `[]`
- Pass condition: the output is not empty. Report the best pair.
- Fail condition: the output is empty. Report the floor.

## References

- `Ideas/IDEA-0008-natural-live-call-streaming.md`
- `.stageset/runs/20261122-192327-RUN.md`
- `Code/batch/server.py` (`_collect`, `_collect_call_first_quiet`)
- `Code/probes/probe_call_admission.py`
