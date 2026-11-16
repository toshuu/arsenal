<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0004
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/coding-ssld-016-t4.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-016-t4.md
@stageset implemented_in: .stageset/sessions/coding-ssld-016-t4.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: GPU memory at B=256

## Goal

List the largest GPU memory items at B=256 before any design work. Find out
whether the voice state, the KV cache, the activations or the cudnn workspace
fills the T4.

This is SSLD-016 step 2.

## Probe instructions

- Run `python Code/probes/probe_memory.py --bs 192,224,256`.
- Open one child process per B. Load the model, build the stream, run one burst.
- Record `torch.cuda.memory_summary()` and `max_memory_allocated`,
  `max_memory_reserved`, and the free bytes after the burst.
- Record named module and buffer sizes: model weights, Mimi state, flow state,
  voice state, activations.
- Write only `Code/probes/out/probe_memory.json`.
- Catch OOM and keep the partial record.

## Measurements

- `per_b[B].max_allocated_mb`, `max_reserved_mb`, `free_after_mb`, `oom`.
- `per_b[B].voice_state_mb`, `flow_state_mb`, `mimi_state_mb`.
- A top-10 item list with name and MB.

## Edge cases

- A B that OOMs can still report the state sizes if you measure before the run.
- Clear the cache between B values in the same child, or use one child per B.

## Checks

### CHECK-MEM-01 - profile exists

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_memory.json')); print(len(d['per_b']) >= 2 and 'top' in d)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: a missing key or a non-zero exit code.

### CHECK-MEM-02 - largest item named

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_memory.json')); print(all('mb' in x for x in d['top']))"`
- Predicted output: `True`
- Pass condition: every top item has an MB value.
- Fail condition: any item has no size.

## References

- `LivingDocs/SSLD-016-single-t4.md`
