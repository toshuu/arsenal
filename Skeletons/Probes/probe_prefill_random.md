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
@stageset last_updated_in: .stageset/sessions/coding-ssld-008-randomized-lever-probe.md
@stageset implemented_in: .stageset/sessions/coding-ssld-008-randomized-lever-probe.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: randomized prefill lever probe

## Goal

Repeat the Phase C lever probe with random order and 3 bursts. Remove the
run-order bias. Pick one lever pair for B=96 and B=128 on one GPU.

## Probe instructions

- Run `python Code/probes/probe_prefill_random.py` from the repository root.
- The script uses FP16, unique texts, random order, and 3 bursts.
- Voice lengths: 6.5, 4.0, 3.0, 2.0 seconds. First chunk caps: 50, 24, 16 tokens.
- Batch sizes: 96 and 128.
- It writes only `Code/probes/out/probe_prefill_random.json` and the per-run JSON files in the same folder.
- Do not change model weights, project files, services, or external state.

## Expected observations

- The JSON has `gpu_name`, `seed`, `bursts`, and 24 `results`.
- The script prints `PREFILL_RANDOM_DONE`.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-19 - Random order removes the run-order bias seen in the first probe. [UNVERIFIED]
ASSUMPTION: A-20 - 3 bursts give a stable p95 on one T4. [UNVERIFIED]

## Checks

### CHECK-PREFILL-RANDOM-01 - output shape

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_prefill_random.json')); print(len(d['results']) == 24 and bool(d['gpu_name']) and d['bursts'] == 3)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the file is missing, the row count is not 24, the GPU name is empty, or bursts is not 3.

### CHECK-PREFILL-RANDOM-02 - a pair meets both batch sizes

- Command: `python Code/probes/pick_lever.py`
- Predicted output: starts with `BEST voice=`.
- Pass condition: exit code 0 and a line that starts with `BEST voice=`.
- Fail condition: no pair holds p95 under 350 ms at both B=96 and B=128.

## References

- `Ideas/optimization-strategy.md`
- `Skeletons/Probes/probe_prefill_levers.md`
- `Code/probes/bench_batch_server.py`
