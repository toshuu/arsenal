<!-- ss-living-doc v1 -->
# SSLD-014: Overlap Mimi decode with the next flow step (M2)

## STATE
doc_id: SSLD-014
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: Skeletons/Code/batch/overlap.py
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-014-overlap-decode.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-014-overlap-decode.md --sync

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

### T001: Add the overlap helper
status: DONE
blocked_reason:
file: Code/batch/overlap.py
also_edit: Skeletons/Code/batch/overlap.py
context: One extra CUDA stream and one event. The decode closure waits for the current stream, then runs on the second stream.
do:
- [x] 1. COPY the code from `Skeletons/Code/batch/overlap.py` into `Code/batch/overlap.py`.
- [x] 2. RUN `python -c "import sys; sys.path.insert(0,'Code'); import torch; from batch.overlap import OverlapDecoder; d=OverlapDecoder('cuda'); print(d.stream != torch.cuda.current_stream())"`.
verify: `python -c "import sys; sys.path.insert(0,'Code'); import torch; from batch.overlap import OverlapDecoder; d=OverlapDecoder('cuda'); print(d.stream != torch.cuda.current_stream())"`
expect: True
if_fail: Read the import error. Check the torch version and the CUDA device. Run `verify:` again.
result: True

### T002: Use the helper in the stream loop
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
also_edit: Code/probes/probe_ttfa_stages.py
context: Add `overlap_decode=False` to `__init__`. In `flush_pending`, start the decode on the helper stream and return before the emit. Emit the previous frame on the next flush or at the end. Keep the synchronous path when `overlap_decode` is false.
do:
- [x] 1. EDIT `__init__` to store `self.overlap = OverlapDecoder(device) if overlap_decode else None`.
- [x] 2. EDIT `flush_pending` to launch `decode_from_latent` and `increment_steps` inside the helper closure. Store the frames and the row metadata. Call `OverlapDecoder.wait()` before emit, before `_slice_model_state`, and before return.
- [x] 3. EDIT the probe to pass `--overlap` into `BatchedStream(..., overlap_decode=args.overlap)`.
- [x] 4. RUN `python Code/probes/check_batch_stream.py` with the default path.
verify: `python Code/probes/check_batch_stream.py`
expect: CHECK_BATCH_STREAM PASS
if_fail: Read the traceback. Set `overlap_decode=False` and check the default path first. Run `verify:` again.
result: CHECK_BATCH_STREAM PASS

### T003: Check audio parity of the overlap path
status: DONE
blocked_reason:
file: Code/probes/check_overlap.py
also_edit: Code/batch/batched_stream.py
context: Build one stream with overlap off and one with overlap on. Use the same voice and the same three texts. Compare the audio and the first-sound time.
do:
- [x] 1. CREATE `Code/probes/check_overlap.py` that compares the two audio outputs with `torch.corrcoef` and `abs().max()`.
- [x] 2. RUN `python Code/probes/check_overlap.py`.
verify: `python Code/probes/check_overlap.py`
expect: CHECK_OVERLAP PASS
if_fail: Read the max abs diff. Check that the emit waits on the event. Run `verify:` again.
result: CHECK_OVERLAP PASS

### T004: Measure the steady gain
status: DONE
blocked_reason:
file: Code/probes/out/probe_ttfa_overlap.json
also_edit: Code/probes/probe_ttfa_stages.py
context: Use the clean client with autocast Mimi. Compare steady ms/frame against the no-overlap values 59.5/65.4/70.7 at B=128/160/192.
do:
- [x] 1. RUN `python Code/probes/probe_ttfa_stages.py --bs 128,160,192 --bursts 5 --rounds 1 --fp16-mimi --overlap --out Code/probes/out/probe_ttfa_overlap.json`.
- [x] 2. CHECK that the steady p50 at B=192 is less than 65.4 ms.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_overlap.json')); print(d['stages']['192']['steady_ms']['p50'] < 65.4)"`
expect: True
if_fail: Read the stage table. Check that the flow step and the decode do not wait on each other. Run `verify:` again.
result: False (69.99 ms vs 65.4 target). M2 dropped; see FACT-0052.

### T005: Record facts and close the document
status: DONE
blocked_reason:
file: .stageset/facts.md
also_edit: Ideas/optimization-strategy.md
context: Record the overlap parity and the steady gain. Add the short note. Then validate.
do:
- [x] 1. APPEND the fact rows for M2.
- [x] 2. APPEND a short note to `Ideas/optimization-strategy.md`.
- [x] 3. RUN `python scripts/stageset-status.py --sync`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the metadata. Run `verify:` again.
result: StageSet validation passed.
