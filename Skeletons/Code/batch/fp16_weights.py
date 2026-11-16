<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/fp16_weights.py
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

# Implementation: pre-cast FP16 weights

## Purpose

Store one FP16 copy of the decode weights in the image. Load that copy straight
to the GPU. Remove the FP32 to FP16 conversion from each decode call.

This is SSLD-016 step 1.

## Contract

- `save_fp16_weights(model, path)`:
  - Cast every floating parameter of Mimi and the flow backbone to FP16.
  - Keep the flow head, the sampler and the flow net in FP32.
  - Write a state dict plus a small dtype map to `path`.
- `load_fp16_weights(model, path)`:
  - Read the file with `map_location="cuda"`.
  - Copy each tensor into the model parameter with `copy_`.
  - Do not create a second full FP32 copy on the GPU.
- The Mimi state tensors must use the same dtype as the Mimi weights.

## Edge cases

- A mixed dtype breaks the conv path on T4. Cast the Mimi state too.
- The file must be built at image time. Never build it at boot.
- If load time grows by more than 100 ms, stop and use autocast only.

## Checks

### CHECK-FP16W-01 - parity

- Command: `python Code/probes/check_fp16_weights.py`
- Predicted output: `CHECK_FP16_WEIGHTS PASS`
- Pass condition: minimum row correlation 0.999 or more.
- Fail condition: any other output or a non-zero exit code.

### CHECK-FP16W-02 - boot and steady

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print(d['fp16_weights']['boot_delta_ms'] < 100)"`
- Predicted output: `True`
- Pass condition: the delta is below 100 ms and steady ms per frame is lower.
- Fail condition: more boot time with no steady gain.

## References

- `LivingDocs/SSLD-016-single-t4.md`
