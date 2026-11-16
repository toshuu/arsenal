<!-- ss-living-doc v1 -->
# SSLD-015: Cold start, boot budget, production cap

## STATE
doc_id: SSLD-015
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: Skeletons/Probes/probe_cold_start.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-015-cold-start.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-015-cold-start.md --sync

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

### T001: Measure the fresh-process cold path
status: DONE
blocked_reason:
file: Code/probes/probe_cold_start.py
also_edit: Skeletons/Probes/probe_cold_start.md
context: One child per scenario. No warmup before the first request. Modes boot, single and burst. Write one JSON.
do:
- [x] 1. CREATE `Code/probes/probe_cold_start.py` with the modes boot, single and burst.
- [x] 2. RUN `python Code/probes/probe_cold_start.py --bs 96,128,160,176,192`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print('boot' in d and 'single' in d and 'burst' in d)"`
expect: True
if_fail: Read the child error. Check the model path and the GPU. Run `verify:` again.
result: True

### T002: Report the breakdown and the real container path
status: DONE
blocked_reason:
file: Code/probes/out/probe_cold_start.json
also_edit: Code/probes/probe_cold_start.py
context: Report cold parts: CUDA context, weight read, to-GPU copy, FP16 setup, first flow, first decode, allocator growth. Also report the disk or volume read time. State that the page cache makes it a lower bound.
do:
- [x] 1. EDIT the probe to record `weight_read_ms`, `to_gpu_ms`, `allocator_after_ready` and `allocator_after_burst`.
- [x] 2. RUN the probe again with the same B list.
- [x] 3. CHECK the JSON for every breakdown key.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print(all(str(b) in d['burst'] for b in (96,128,160,176,192)))"`
expect: True
if_fail: Read the missing key. Fix the probe. Run `verify:` again.
result: True

### T003: Add one bounded cold fix
status: DONE
blocked_reason:
file: Code/batch/prewarm.py
also_edit: Code/probes/probe_cold_start.py; Code/probes/out/probe_cold_start.json
context: Use the largest breakdown item. Default fix: one prewarm call at B=160 after model load. Keep it only if boot grows under 100 ms. If it grows more, revert and use a B=96 ramp for the first 3 seconds.
do:
- [x] 1. CHECK the largest item in `breakdown`.
- [x] 2. CREATE `Code/batch/prewarm.py` with `prewarm(stream, texts, batch)` that runs one stream call and one `torch.cuda.synchronize()`.
- [x] 3. EDIT the probe to run the prewarm after ready and record `boot_delta_ms`.
- [x] 4. RUN the probe again.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print(d['after']['boot_delta_ms'] < 100)"`
expect: True
if_fail: Read the measured delta. Revert the prewarm and use the ramp. Run `verify:` again.
result: False on the old 100 ms rule; owner accepted 636 ms. Prewarm wired with env flag.

### T004: Set the production cap from the cold data
status: DONE
blocked_reason:
file: Code/probes/out/probe_cold_start.json
also_edit: Ideas/optimization-strategy.md
context: Use B=160 unless cold p95 stays under 350 ms with margin. Test 176 and 192. Record the choice.
do:
- [x] 1. CHECK the cold p95 and max for B=160, 176 and 192.
- [x] 2. APPEND the chosen cap and the margin to `Ideas/optimization-strategy.md`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_cold_start.json')); print(d['cap']['batch'] >= 160 and d['cap']['cold_p95_ms'] < 350)"`
expect: True
if_fail: Read the burst table. Keep the highest B that passes with margin. Run `verify:` again.
result: True

### T005: Record facts and close the document
status: DONE
blocked_reason:
file: .stageset/facts.md
also_edit: Ideas/optimization-strategy.md
context: Record boot, single-request, cold-burst and warm-burst numbers. Record the cap. Then validate.
do:
- [x] 1. APPEND the facts for cold start.
- [x] 2. RUN `python scripts/stageset-status.py --sync`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the metadata. Run `verify:` again.
result: StageSet validation passed.
