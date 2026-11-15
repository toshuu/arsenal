<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0003
@stageset status: DONE
@stageset priority: P1
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/ideation-phase-c-levers.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-007-prefill-levers.md
@stageset implemented_in: .stageset/sessions/coding-ssld-007-prefill-levers.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Phase C prefill levers

## Goal

Measure how a shorter voice prompt and a capped first text chunk change p95
TTFA at high batch on one GPU. Record the GPU name so the test can be repeated
on L4.

## Probe instructions

- Run `python Code/probes/probe_prefill_levers.py` from the repository root.
- The script uses FP16 and unique texts. It writes only `Code/probes/out/probe_prefill_levers.json`.
- Voice lengths: 6.5, 4, 3, 2 seconds. First chunk caps: 50, 24, 16 tokens.
- Batch sizes: 96 and 128. Bursts: 2.
- Do not change model weights, project files, services, or external state.

## Expected observations

- The JSON has `gpu_name`, `config`, and a list of `results`.
- Every result has `voice_seconds`, `first_tokens`, `batch`, `p95_ms`, `p50_ms`, and `under_350`.
- The script prints `PREFILL_LEVERS_DONE`.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-17 - A shorter voice prompt lowers TTFA at fixed B. [UNVERIFIED]
ASSUMPTION: A-18 - A capped first chunk lowers the p95 tail. [UNVERIFIED]

## Checks

### CHECK-PREFILL-LEVERS-01 - output shape

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_prefill_levers.json')); print(len(d['results']) == 24 and bool(d['gpu_name']))"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the file is missing, the result count is not 24, or the GPU name is empty.

### CHECK-PREFILL-LEVERS-02 - best point meets target

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_prefill_levers.json')); print(min(r['p95_ms'] for r in d['results']) < 350)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: every point is 350 ms or more.

## References

- `Ideas/optimization-strategy.md`
- `Skeletons/Code/batch/batched_stream.py`
- `Code/probes/bench_batch_server.py`
