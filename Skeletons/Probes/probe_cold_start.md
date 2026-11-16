<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0004
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/coding-ssld-015-cold.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-015-cold.md
@stageset implemented_in: .stageset/sessions/coding-ssld-015-cold.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: cold start on a fresh process

## Goal

Measure the cold cost that the soak misses. Report boot time, single-request
TTFA, and first-burst TTFA on a fresh process. Split the cost into parts.

This is step 1 of the post-SSLD-014 plan.

## Probe instructions

- Run `python Code/probes/probe_cold_start.py --bs 96,128,160,176,192`.
- The parent process spawns one child per scenario. Each child loads the model
  from disk and does no warmup before its one burst.
- Modes: `boot`, `single`, `burst`.
- Write only `Code/probes/out/probe_cold_start.json`.
- Do not change model weights or project files during a run.

## Measurements

- `boot.phases_ms`: import, cuda_init, weight_read, to_gpu, fp16, ready.
- `boot.total_ms`: child script start to ready.
- `single.ttfa_ms`: first ever stream call, B=1. `single.warm_ttfa_ms`: second call.
- `burst[B].cold`: p50, p95, max TTFA for the first burst.
- `burst[B].warm`: p50, p95, max for the second burst in the same child.
- `breakdown`: first flow step, first decode, second flow step, allocator bytes.

## Edge cases

- The model file may be in the page cache. Report `weight_read_ms` as a lower
  bound and say so.
- One child can fail. Record the error and continue with the other scenarios.
- Do not count the parent spawn time in the child phase sum.

## Checks

### CHECK-COLD-01 - data present

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print('boot' in d and 'single' in d and 'burst' in d)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: any missing key or a non-zero exit code.

### CHECK-COLD-02 - fresh burst measured

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print(all(str(b) in d['burst'] for b in (96,128,160,176,192)))"`
- Predicted output: `True`
- Pass condition: every B has a cold and a warm record.
- Fail condition: any B is missing.

### CHECK-COLD-03 - boot delta

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print(d['after']['boot_delta_ms'] < 100)"`
- Predicted output: `True`
- Pass condition: the fix adds less than 100 ms to boot.
- Fail condition: 100 ms or more.

## References

- `LivingDocs/SSLD-015-cold-start.md`
