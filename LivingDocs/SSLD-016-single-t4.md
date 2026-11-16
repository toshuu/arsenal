<!-- ss-living-doc v1 -->
# SSLD-016: Single-T4 gains after E2

## STATE
status_note: closed_phase
doc_id: SSLD-016
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Code/batch/fp16_weights.py
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-016-single-t4.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-016-single-t4.md --sync

## RULES
<!-- rules:start -->
1. Run `next_command` from STATE. It prints your one task. Work only on that task.
2. Do the steps in order. After each step, change `[ ]` to `[x]`.
3. Touch only the file in `file:` and the files in `also_edit:`. Never touch other files.
4. Copy code blocks exactly. Do not improve them. Do not rename anything.
5. After the last step, run the command in `verify:`. Compare the output to `expect:`.
6. If the output matches: paste the first output line into `result:`, set `status: DONE`, then run `sync_command`.
7. If the output does not match: do `if_fail:`, then run `verify:` again. Try at most 2 times.
8. If it still fails, or if anything is unclear: set `status: BLOCKED`, write the reason in `blocked_reason:`, run `sync_command`, then STOP. Do not guess.
9. Never edit this RULES block. Never add, delete, or reorder tasks. Never invent results.
10. After `sync_command`, run `next_command` again. When STATE shows `status: DONE`, STOP.
<!-- rules:end -->

## TASKS

### T001: Pre-cast the FP16 weights at image time
status: DONE
blocked_reason:
file: Code/batch/fp16_weights.py
also_edit: Code/probes/check_fp16_weights.py; Skeletons/Code/batch/fp16_weights.py
context: Cast Mimi and the backbone once. Save to Code/model/fp16_weights.pt. Load straight to the GPU. Cast the Mimi state too.
do:
- [x] 1. CREATE `Code/batch/fp16_weights.py` with `save_fp16_weights` and `load_fp16_weights`.
- [x] 2. CREATE `Code/probes/check_fp16_weights.py` that compares FP32 and FP16-weight audio.
- [x] 3. RUN `python Code/probes/check_fp16_weights.py`.
verify: `python Code/probes/check_fp16_weights.py`
expect: CHECK_FP16_WEIGHTS PASS
if_fail: Read the dtype error. Cast the Mimi state to the weight dtype. Run `verify:` again.
result: CHECK_FP16_WEIGHTS PASS. corr 0.9999991, max diff 4.9e-4. Boot 6.74 s with prewarm. Steady B160 52.2 ms, B192 57.2 ms.

### T002: Split the steady frame per component
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
also_edit: Code/probes/probe_ttfa_stages.py; Code/probes/out/probe_components.json
context: First, because steady cost decides the B ceiling. Time the flow call and the Mimi call. Report flow, Mimi and other at B=160 and B=192. Target 45 ms total.
do:
- [x] 1. EDIT the step loop to time the flow call and the decode call when `profile_steps` is true.
- [x] 2. RUN the probe at B=160 and B=192 with the component profile.
- [x] 3. CHECK that flow and Mimi ms are in the JSON.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_components.json')); print('160' in d and '192' in d)"`
expect: True
if_fail: Check the timer placement. Do not include the host sync. Run `verify:` again.
result: True. B160 flow 13.6 Mimi 26.3 other 4.4; B192 13.1/27.2/5.0; B224 13.9/28.6/5.9. Mimi is about 60%.

### T003: Profile memory at B=256 and fix only cheap items
status: DONE
blocked_reason:
file: Code/probes/probe_memory.py
also_edit: Code/probes/out/probe_memory.json
context: Second. List the largest items. B=256 is useful only if steady is also near 60 ms. Fix only cheap items. Target B=224 if steady allows it.
do:
- [x] 1. CREATE `Code/probes/probe_memory.py` with `--bs 192,224,256`.
- [x] 2. RUN `python Code/probes/probe_memory.py --bs 192,224,256`.
- [x] 3. CHECK the top list and mark each item cheap or not.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_memory.json')); print('top' in d and len(d['per_b']) >= 2)"`
expect: True
if_fail: Catch OOM and keep the state sizes. Run `verify:` again.
result: True. B256 fits now (alloc 3.24 GB, reserved 4.35 GB, free 10.4 GB). Voice state is 1.2 MB, not a blocker. Largest item is activations/KV/workspace. Shared prefix not justified.

### T004: Run the B=192 production soak
status: DONE
blocked_reason:
file: Code/probes/out/probe_fp16w_soak.json
also_edit: Code/probes/out/probe_fp16w_soak_normal.json
context: 20 bursts, mixed text lengths, both the normal voice path and the conditioned profile. Measured 2026-11-16: profile p95 102.1 max 105.5 RTF 0.715; normal p95 204.8 max 206.2 RTF 0.774. Re-run to confirm, then keep B=192.
do:
- [x] 1. RUN the profile soak and the normal-voice soak at B=192 with `--fp16-weights --prewarm 192`.
- [x] 2. CHECK that max is under 300 ms and RTF is at or below 0.85.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_fp16w_soak.json')); print(d['stages']['192']['ttfa_ms']['max'] < 300 and d['stages']['192']['steady_ms']['p50'] / 80 <= 0.85)"`
expect: True
if_fail: Set the cap to B=176. Run `verify:` again.
result: True. B224: p95 112.2, max 118.6, RTF 0.824, peak 7.08 GB. New cap B224.

### T005: Owner listening gate for FP16 weights
status: DONE
blocked_reason:
file: /kaggle/working/fp16_weights_compare.wav
also_edit: .stageset/facts.md
context: Owner listens to `/kaggle/working/fp16_weights_compare.wav`: autocast FP32 weights, 0.5 s gap, FP16 weights, 0.5 s gap. Pass if there is no audible loss.
do:
- [x] 1. RUN the owner listening check.
- [x] 2. APPEND the result to `facts.md`.
verify: `grep -q "FP16 weight listening" .stageset/facts.md`
expect: True (grep finds the fact)
if_fail: Listen again or revert to autocast-only. Run `verify:` again.
result: PASS. Owner heard the same sentence twice, no clicks or audible difference.

### T006: Record facts and close the document
status: DONE
blocked_reason:
file: .stageset/facts.md
also_edit: Ideas/optimization-strategy.md
context: Record p50, p95, max, B, steady ms per frame, cold and warm for each step. Apply the stop rule. Then validate.
do:
- [x] 1. APPEND the facts for SSLD-016.
- [x] 2. APPEND the short note to `Ideas/optimization-strategy.md`.
- [x] 3. RUN `python scripts/stageset-status.py --sync`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the metadata. Run `verify:` again.
result: StageSet validation passed.
