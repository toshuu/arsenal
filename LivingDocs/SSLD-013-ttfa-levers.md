<!-- ss-living-doc v1 -->
# SSLD-013: TTFA levers E1, E4, E2, E3 and max B

## STATE
doc_id: SSLD-013
status: DONE
current_task: T007
tasks_done: 7
tasks_total: 7
skeleton: Skeletons/Code/batch/batched_stream.py
spec_revision: 6
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-013-ttfa-levers.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-013-ttfa-levers.md --sync

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

### T001: Run the max-B sweep with the clean client
status: DONE
blocked_reason:
file: Code/probes/out/probe_ttfa_maxb.json
also_edit: Code/probes/probe_ttfa_stages.py
context: Extend the E0 probe with frames, fp16-mimi, decode-group, OOM handling and steady ms. Run B=128,160,192,224,256.
do:
- [x] 1. RUN `python Code/probes/probe_ttfa_stages.py --bs 128,160,192,224,256 --bursts 3 --rounds 1 --out Code/probes/out/probe_ttfa_maxb.json`.
- [x] 2. CHECK that B=256 reports OOM and that the other B values have data.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_maxb.json')); print(sorted(d['stages']) == ['128','160','192','224','256'] and len(d['errors']) == 3)"`
expect: True
if_fail: Read the server output. Check the profile file and GPU free memory. Run `verify:` again.
result: True

### T002: Remove text prep from the critical path
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
also_edit: Skeletons/Code/batch/batched_stream.py
context: Prep is 65 ms at B=128. Use one worker pool and one batched embedding call. Keep a text id cache. Right-align rows.
do:
- [x] 1. EDIT `_text_ids` and `_encode_texts` as the skeleton shows. Use one `conditioner(tokens)` call.
- [x] 2. EDIT `_build_prefixes` to place the voice block after the leading pad. Keep parity with the old layout.
- [x] 3. RUN `python Code/probes/check_batch_stream.py`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_maxb.json')); print(d['stages']['128']['prep_ms']['p50'] < 10)"`
expect: True
if_fail: Read the stage table. Check that `_encode_texts` makes one conditioner call. Run `verify:` again.
result: True

### T003: Remove the per-row emit cost
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
also_edit: Skeletons/Code/batch/batched_stream.py
context: Emit is 26 ms at B=128. Append frame views. Keep a row_ids map. No per-row clone or item call.
do:
- [x] 1. EDIT the flush and emit path as the skeleton shows.
- [x] 2. RUN `python Code/probes/check_batch_stream.py`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_maxb.json')); print(d['stages']['128']['emit_ms']['p50'] < 5)"`
expect: True
if_fail: Search for `.clone()` and `.item()` in the step loop. Remove them. Run `verify:` again.
result: True

### T004: Run the Mimi decoder under FP16 autocast
status: DONE
blocked_reason:
file: Code/batch/fp16.py
also_edit: Code/probes/check_mimi_fp16.py; Skeletons/Code/batch/fp16.py
context: E2. Keep Mimi parameters in FP32. Use autocast. Do not call `mimi.half()`.
do:
- [x] 1. EDIT `enable_fp16_backbone` to add `mimi_fp16=False` and the autocast wrapper.
- [x] 2. RUN `python Code/probes/check_mimi_fp16.py`.
- [x] 3. RUN the probe with `--fp16-mimi` at B=128,160,192,224.
verify: `python -c "import json; d=json.load(open('Code/probes/out/check_mimi_fp16.json')); print(d['min_corr'] >= 0.99 and d['max_abs_diff'] < 0.01)"`
expect: True
if_fail: Check the dtype error. Keep the parameters in FP32. Run `verify:` again.
result: True

### T005: Sweep decode_group for steady frames
status: DONE
blocked_reason:
file: Code/probes/out/probe_ttfa_dg4.json
also_edit: Code/probes/out/probe_ttfa_dg2.json
context: E3. Compare steady ms per frame at B=192 with decode_group 1, 2, 4. Keep group 1 at step 0.
do:
- [x] 1. RUN the probe with decode groups 2 and 4 at B=192.
- [x] 2. CHECK steady p50 against the group 1 value of 70.68 ms.
verify: `python -c "import json; a=json.load(open('Code/probes/out/probe_ttfa_dg2.json'))['stages']['192']['steady_ms']['p50']; b=json.load(open('Code/probes/out/probe_ttfa_mimi_autocast.json'))['stages']['192']['steady_ms']['p50']; print(a > b)"`
expect: True
if_fail: Read the stage tables. Keep decode_group 1. Run `verify:` again.
result: True

### T006: Re-run the B=144 and B=160 soaks with the clean client
status: DONE
blocked_reason:
file: Code/probes/out/soak_b144_summary.json
also_edit: Code/probes/out/probe_ttfa_soak_144_160.json
context: Supersede the blocked SSLD-010 T005. Use 20 bursts per B. Use the autocast Mimi path.
do:
- [x] 1. RUN `python Code/probes/probe_ttfa_stages.py --bs 144,160 --bursts 20 --rounds 1 --fp16-mimi --out Code/probes/out/probe_ttfa_soak_144_160.json`.
- [x] 2. CHECK that both B values have 100% of rows under 350 ms.
verify: `python -c "import json; d=json.load(open('Code/probes/out/soak_b144_summary.json')); print(d['under_pct'] == 100.0 and d['ttfa_p95_ms'] < 350)"`
expect: True
if_fail: Read the soak output. Check for OOM. Run `verify:` again.
result: True

### T007: Record facts and close the document
status: DONE
blocked_reason:
file: .stageset/facts.md
also_edit: Ideas/optimization-strategy.md
context: Record the E1, E2, E3, E4 and soak facts. Add the short note to the strategy idea. Then validate.
do:
- [x] 1. APPEND the fact rows for E1, E2, E3, E4, max B and the clean soaks.
- [x] 2. APPEND a short note to `Ideas/optimization-strategy.md`.
- [x] 3. RUN `python scripts/stageset-status.py --sync`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the metadata. Run `verify:` again.
result: StageSet validation passed.
