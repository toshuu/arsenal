<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0004
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/ideation-ttfa-burst-gain.md
@stageset last_updated_in: .stageset/sessions/coding-ttfa-stages-e0.md
@stageset implemented_in: .stageset/sessions/coding-ttfa-stages-e0.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: TTFA stage breakdown with a separate load generator

## Goal

Find what fills the 50 to 180 ms gap between TTFA compute (173 ms) and p95
TTFA at B=128. Split the gap into stage and queue cost. Report p50 and p95
for each stage at B=128 and B=160 on one T4.

This is lever E0 of `Ideas/IDEA-0004-ttfa-burst-gain.md`.

## Probe instructions

- Run `python Code/probes/probe_ttfa_stages.py --bs 128,160 --bursts 5 --rounds 2`
  from the repository root.
- The tool starts one server child process. The child owns the model, the
  voice profile, and one `BatchedStream`.
- The parent process is the load generator. It does no GPU work. It sends one
  burst, waits for the result, and sends the next burst. It records `t_send`.
- The child records absolute `time.perf_counter()` values for each stage.
  The clock is system-wide on Linux, so the parent can subtract `t_send`.
- It writes only `Code/probes/out/probe_ttfa_stages.json`.
- Do not change model weights, project files, services, or external state.

## Measurements

For each burst and each row:

- `queue_ms`: `stream_start - t_send`. Time in the IPC queue and admission.
- `prep_ms`: `prep_done - prep_start`. Text prep on the CPU.
- `state_ms`: `state_done - prep_done`. State clone and padding.
- `cond_ms`: `cond_done - state_done`. Conditioning forward.
- `flow0_ms`: `flow0_done - cond_done`. Step 0 flow forward.
- `mimi0_ms`: `mimi0_done - flow0_done`. Step 0 Mimi decode.
- `emit_ms`: `first_emit - mimi0_done`. First-chunk emit path.
- `ttfa_ms`: `first_emit - t_send`. End-to-end first chunk.
- `compute_ms`: sum of prep, state, cond, flow0, mimi0, emit.
- `gap_ms`: `ttfa_ms - compute_ms - queue_ms`. Kernel waits and jitter.

The tool also samples GPU utilisation with `nvidia-smi` and CPU utilisation
from `/proc/stat` every 200 ms while bursts run.

## Expected observations

- The JSON has `gpu_name`, `bs`, `bursts`, `rounds`, `stages`, `ttfa`, and
  `util`.
- `stages` has one entry for each name above. Each entry has `p50` and `p95`.
- The script prints `TTFA_STAGES_DONE`.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-30 - `time.perf_counter()` uses a system-wide monotonic clock on this Linux host. [UNVERIFIED]
ASSUMPTION: A-31 - A separate process removes the load generator CPU bias. [UNVERIFIED]
ASSUMPTION: A-32 - The stage marks do not add more than 1 ms to TTFA. [UNVERIFIED]

## Checks

### CHECK-TTFA-STAGES-01 - output shape

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_stages.json')); print(sorted(d['bs']) == [128,160] and d['bursts'] == 5 and bool(d['gpu_name']))"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the file is missing, the batch list is not `[128, 160]`, bursts is not 5, or the GPU name is empty.

### CHECK-TTFA-STAGES-02 - stage table complete

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_stages.json')); need={'queue_ms','prep_ms','state_ms','cond_ms','flow0_ms','mimi0_ms','emit_ms','ttfa_ms','compute_ms','gap_ms'}; print(all(need <= set(v) for v in d['stages'].values()) and all(v['ttfa_ms']['p95'] is not None for v in d['stages'].values()))"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: a stage name is missing or a p95 value is null.

### CHECK-TTFA-STAGES-03 - probe finished

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_stages.json')); print(d['done'])"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the probe did not finish or the key is absent.

## References

- `Ideas/IDEA-0004-ttfa-burst-gain.md`
- `Skeletons/Code/batch/batched_stream.py`
- `Code/probes/bench_batch_server.py`
- `.stageset/facts.md` (FACT-0041)
