<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/maintenance-phase4-confirm-review.md
@stageset last_updated_in: .stageset/sessions/maintenance-phase4-quiet-review.md
@stageset implemented_in: .stageset/sessions/coding-phase4-quiet.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Phase 4 quiet formation at B=320

## Goal

Test if a quiet formation policy with buckets off meets the 350 ms gate at B=320
on a real server. The full 150 ms window wait must not be paid.

## Method

- Use a separate-process uvicorn server. Start a fresh server for each policy.
- Set cap 640 and queue 4096. Set the default window to 150 ms.
- Use B=320 only.
- Use `sentence` and `utterance`.
- Use 6 calls per cell. Call 0 and call 1 are cold. Call 2 to 5 are warm.
- Set the policy env before the server starts.
- Record `batch_sizes`, p95, p50, errors, and peak VRAM.

## Policies

| Name | Target | Quiet ms | Hard cap ms | Buckets |
| --- | ---: | ---: | ---: | ---: |
| target64 | 64 | 0 | 0 | 1 |
| q2h20_nb | 640 | 2 | 20 | 0 |
| q2h30_nb | 640 | 2 | 30 | 0 |
| q3h40_nb | 640 | 3 | 40 | 0 |

The `target64` policy is a control. It shows the effect of a low target.

## Decision rule

- A policy passes when every warm row for both modes has `batch_sizes` equal to
  `[320]` and the worst warm p95 is less than or equal to 350 ms.
- If a policy passes, report its name and p95. The planner wires it.
- If no policy passes, report the floor. Lock the 350 ms operating point at
  B=224 `sentence`.

## Safety boundary

- Do not change model weights.
- Do not change app code. This probe adds one script and writes
  `Code/probes/out/`.
- Do not send data off the machine.
- Stop each server after its policy.

## Assumptions

ASSUMPTION: A-53 - A quiet policy with buckets off stops the 1-row early batch.
[UNVERIFIED]

ASSUMPTION: A-54 - B=320 at `first_max_frames=8` fits one T4. [UNVERIFIED]

## Checks

### CHECK-PHASE4-QUIET-01 - probe JSON

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_quiet/quiet.json')); print(len(d['rows']), len(d['policies']))"`
- Predicted output: `48 4`
- Pass condition: 48 rows and 4 policies.
- Fail condition: missing file or a wrong count.

### CHECK-PHASE4-QUIET-02 - policy pass table

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_quiet/quiet.json')); rows=d['rows']; out={}; [out.setdefault(p['name'],[]).append(r) for p in d['policies'] for r in rows if r['policy']==p['name'] and r['warm']]; print({k: (all(r['batch_sizes']==[320] for r in v), max(r['p95'] for r in v)) for k,v in out.items()})"`
- Predicted output: a dict with one `(bool, max p95)` pair for each policy
- Pass condition: at least one pair has `True` for the batch check and a max p95
  less than or equal to 350.
- Fail condition: no pair passes. Report the floor.

## References

- `Ideas/IDEA-0008-natural-live-call-streaming.md`
- `.stageset/runs/20261122-195007-RUN.md`
- `Code/batch/server.py` (`_collect`, `_collect_call_first_quiet`)
