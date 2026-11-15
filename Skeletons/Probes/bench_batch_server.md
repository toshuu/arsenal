<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0003
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/ideation-batch-server.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-006-batch-harness.md
@stageset implemented_in: .stageset/sessions/coding-ssld-006-batch-harness.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: batched streaming burst ceiling

## Goal

Measure the highest lockstep batch N that keeps p95 first non-silent latency at
or below 350 ms on one T4. Also measure aggregate RTF, wall time, peak VRAM, and
B=1 versus B=32 parity.

## Probe instructions

- Run `python Code/probes/bench_batch_server.py --bs 30,32,34,35,36 --bursts 5 --parity-b 32 --out Code/probes/out/bench_batch_server_knee.json` from the repository root.
- The script writes only the JSON file under `Code/probes/out/`.
- Do not change model weights, project files, services, or external state.
- Do not expose secrets or credentials.

## Commands

```bash
python Code/probes/bench_batch_server.py --bs 30,32,34,35,36 --bursts 5 --parity-b 32 --out Code/probes/out/bench_batch_server_knee.json
```

## Expected observations

- The command prints a table and ends with `BENCH_BATCH_SERVER_DONE`.
- The JSON has `results`, `parity`, `device`, `torch`, and `cuda`.
- B=30 has p95 TTFA below 350 ms.
- B=32 has p95 TTFA below 350 ms but a small tail above 350 ms.
- B=34 has p95 TTFA at or above 350 ms.
- The B=32 parity max absolute difference is below 1e-3 and the correlation is 1.0.
- Peak VRAM at B=32 is below 3 GB.
- Aggregate RTF at B=32 is below 0.02.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-13 - `on_chunk` is called once per row per emitted frame, in row order. [UNVERIFIED]
ASSUMPTION: A-14 - The first non-silent sample index divided by samples-per-frame gives the frame index in `frame_times`. [UNVERIFIED]
ASSUMPTION: A-15 - Reusing one `BatchedStream` for repeated bursts does not leak state. [UNVERIFIED]
ASSUMPTION: A-16 - `torch.cuda.max_memory_allocated` after `reset_peak_memory_stats` reports the burst peak. [UNVERIFIED]

## Checks

### CHECK-BENCH-BATCH-01 - parity

- Command: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); print(d['parity']['max_abs_diff'] < 1e-3)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the file is missing or the value is 1e-3 or more.

### CHECK-BENCH-BATCH-02 - B=32 p95 and tail

- Command: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); s={x['batch']:x['summary'] for x in d['results']}[32]; print(s['ttfa_p95_ms'] < 350 and s['under_350_fraction'] >= 0.95)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: B=32 is missing, p95 is 350 or more, or the under-350 fraction is below 0.95.

### CHECK-BENCH-BATCH-03 - B=30 p95

- Command: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); s={x['batch']:x['summary'] for x in d['results']}[30]; print(s['ttfa_p95_ms'] < 350)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: B=30 is missing or its p95 is 350 or more.

## References

- `Ideas/optimization-strategy.md`
- `Code/batch/batched_stream.py`
- `LivingDocs/SSLD-006-batch-harness.md`
- `Code/probes/out/bench_batch_server_knee.json`
