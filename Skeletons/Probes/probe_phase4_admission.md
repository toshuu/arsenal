<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/plan-phase4-admission.md
@stageset last_updated_in: .stageset/sessions/plan-phase4-admission.md
@stageset implemented_in: .stageset/sessions/coding-phase4-admission.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Phase 4 admission and cap

## Goal

Answer one question with evidence: is the B>=320 split in Phase 2 caused by the
default `ARSENAL_MAX_BATCH` and `ARSENAL_MAX_ROWS` cap of 224, or by a real
admission limit?

The earlier in-process sweep `Code/probes/out/admission_sweep.json` shows B=384
in one batch at p95 293 ms when the cap is 640. That sweep used the legacy
16-token first chunk. This probe repeats the test on the current code with the
`sentence` and `utterance` quality modes.

## Method

- Start one local uvicorn server with `ARSENAL_DEBUG=1`.
- Raise `ARSENAL_MAX_BATCH`, `ARSENAL_MAX_ROWS`, `ARSENAL_BATCH_TARGET`, and
  `ARSENAL_CALL_FIRST_MAX_BATCH` to 640.
- Run `/debug/callramp` with `first_only=1`, `first_max_frames=8`, `window=5`.
- Use `stream_mode` `sentence` and `utterance`.
- Use B = 224, 320, 448.
- Use 4 reps per cell. Rep 0 is cold. Use reps 1 to 3 as warm.
- Record first-byte p50, p95, errors, batch sizes, and peak VRAM.

## Output

- One JSON file at `Code/probes/out/phase4_admission/admission.json`.
- Each row has `mode`, `b`, `rep`, `warm`, `p50`, `p95`, `errors`,
  `batch_sizes`, `vram_after`.

## Decision rule

- If a warm cell at B=320 forms one batch of 320 rows and p95 <= 350 ms, the
  Phase 2 split is a cap artifact. Then Phase 4 is a cap and formation change.
  No `BatchedStream` rewrite.
- If a warm cell at B=320 splits, or p95 > 350 ms, then admission needs a code
  change. The planner writes a new skeleton revision.

## Safety boundary

- Do not change model weights.
- Do not edit project code. This probe only adds a probe script and writes
  `Code/probes/out/`.
- Do not send data off the machine.
- Do not claim a pass without the JSON file.
- Stop the server after the run.

## Assumptions

ASSUMPTION: A-47 - `/debug/callramp` returns `batch_sizes` and `first_byte_ms`
per run. [UNVERIFIED]

ASSUMPTION: A-48 - B=448 at `first_max_frames=8` fits one T4. [UNVERIFIED]

## Checks

### CHECK-PHASE4-ADM-01 - probe JSON

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_admission/admission.json')); print(len(d['rows']), sorted({r['b'] for r in d['rows']}))"`
- Predicted output: `24 [224, 320, 448]`
- Pass condition: the file has 24 rows and all three B values.
- Fail condition: missing file, wrong row count, or a missing B value.

### CHECK-PHASE4-ADM-02 - single batch at B=320

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_admission/admission.json')); w=[r for r in d['rows'] if r['b']==320 and r['warm']]; print(all(r['batch_sizes']==[320] for r in w))"`
- Predicted output: `True`
- Pass condition: each warm B=320 row has `batch_sizes` equal to `[320]`.
- Fail condition: any warm B=320 row has more than one batch. Report the split.

### CHECK-PHASE4-ADM-03 - 350 ms at B=320

- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_admission/admission.json')); w=[r for r in d['rows'] if r['b']==320 and r['warm']]; print(min(r['p95'] for r in w))"`
- Predicted output: a number less than or equal to 350
- Pass condition: the best warm B=320 p95 is less than or equal to 350 ms.
- Fail condition: the best warm B=320 p95 is greater than 350 ms. Report the floor.

## References

- `Ideas/IDEA-0008-natural-live-call-streaming.md`
- `Code/probes/probe_call_admission.py`
- `.stageset/runs/20261122-152530-RUN.md`
