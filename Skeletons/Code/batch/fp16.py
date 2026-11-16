<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/fp16.py
@stageset source_idea: IDEA-0004
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/coding-ssld-013-ttfa-levers.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-013-ttfa-levers.md
@stageset implemented_in: .stageset/sessions/coding-ssld-013-ttfa-levers.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: FP16 helpers

## Purpose

Provide the FP16 backbone path. Provide an optional FP16 Mimi decode path.

This is lever E2 of `Ideas/IDEA-0004-ttfa-burst-gain.md`.

## Contract

- `enable_fp16_backbone(model, mimi_fp16=False)`:
  - Always convert the flow_lm backbone to FP16.
  - Keep the head, the sampler, and the flow net in FP32.
  - When `mimi_fp16` is false, keep the Mimi decoder in FP32.
  - When `mimi_fp16` is true, run the Mimi decoder under CUDA autocast with
    dtype float16. Keep the Mimi parameters and state in FP32. Do not call
    `model.mimi.half()`. A mixed dtype breaks the conv state on T4.
  - Return the model.

## Edge cases

- The first autocast decode is slow. It autotunes kernels. Warm up before you
  measure.
- Autocast does not change the output dtype of the public API. The stream
  returns float32 audio.

## Checks

### CHECK-MIMI-FP16-01 - parity

- Command: `python Code/probes/check_mimi_fp16.py`
- Predicted output: `CHECK_MIMI_FP16 PASS`
- Pass condition: exit code 0 and the exact line `CHECK_MIMI_FP16 PASS`.
  The minimum row correlation must be 0.99 or more.
- Fail condition: any other output or a non-zero exit code.

### CHECK-MIMI-FP16-02 - steady gain

- Command: `python -c "import json; a=json.load(open('Code/probes/out/probe_ttfa_maxb.json')); b=json.load(open('Code/probes/out/probe_ttfa_mimi_autocast.json')); print(b['stages']['160']['steady_ms']['p50'] < a['stages']['160']['steady_ms']['p50'])"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the FP16 Mimi steady p50 is not lower than the FP32 Mimi value.

## References

- `Ideas/IDEA-0004-ttfa-burst-gain.md`
- `Code/batch/batched_stream.py`
