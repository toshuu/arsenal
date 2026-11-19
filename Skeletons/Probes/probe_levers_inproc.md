<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0003
@stageset status: DONE
@stageset priority: P1
@stageset spec_revision: 2
@stageset implemented_revision: 2
@stageset planned_in: .stageset/sessions/ideation-phase-c-cleanup.md
@stageset last_updated_in: .stageset/sessions/ideation-phase-c-cleanup.md
@stageset implemented_in: .stageset/sessions/coding-ssld-009-phase-c-cleanup.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: in-process lever comparison

## Goal

Compare voice length and first-chunk cap inside one process. Remove the
cross-process bias. Measure B=96 and B=128 with FP16 on one GPU.

## Probe instructions

- Run `python Code/probes/probe_levers_inproc.py` from the repository root.
- One model load. One process. Interleaved rounds in random order.
- Voice lengths: 6.5, 4.0, 3.0, 2.0 seconds. First chunk caps: 50, 24, 16 tokens.
- Batch sizes: 96 and 128. Bursts: 3.
- It writes only `Code/probes/out/probe_levers_inproc.json`.
- Do not change model weights, project files, services, or external state.

## Expected observations

- The JSON has `gpu_name`, `seed`, `bursts`, and 24 `results`.
- The script prints `LEVERS_INPROC_DONE`.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-21 - One process removes the cross-process bias seen in FACT-0019. [UNVERIFIED]
ASSUMPTION: A-22 - Interleaved rounds remove the order bias. [UNVERIFIED]

## Checks

### CHECK-LEVERS-INPROC-01 - output shape

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_levers_inproc.json')); print(len(d['results']) == 24 and bool(d['gpu_name']) and d['bursts'] == 3)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the file is missing, the row count is not 24, the GPU name is empty, or bursts is not 3.

### CHECK-LEVERS-INPROC-02 - in-process probe is biased

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_levers_inproc.json')); g={(r['voice_seconds'],r['first_tokens'],r['batch']):r['p95_ms'] for r in d['results']}; print(g[(2.0,16,96)] >= g[(4.0,16,96)])"`
- Predicted output: `True`
- Pass condition: the command prints `True`. The biased probe must not rank voice length. See FACT-0023.
- Fail condition: the probe gives a lower p95 for the 2.0 s voice, which would make it look valid.

## References

- `Ideas/optimization-strategy.md`
- `Skeletons/Code/batch/batched_stream.py`
- `Code/probes/bench_batch_server.py`
- `.stageset/runs/20261115-184910-RUN.md`
