<!-- ss-living-doc v1 -->
# SSLD-020: Call-mode server wiring

## STATE
doc_id: SSLD-020
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: Skeletons/Code/batch/server.py
spec_revision: 10
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-020-call-mode-server-wiring.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-020-call-mode-server-wiring.md --sync

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

### T001: Add class-aware imports and job fields
status: DONE
blocked_reason:
file: Code/batch/server.py
context: Add the job class module and the call chunker to the server. Add job_class and mode to Job.
do:
- [x] 1. EDIT `Code/batch/server.py`: add the imports for `batch.call_chunker` and `batch.job_classes`.
- [x] 2. EDIT `Code/batch/server.py`: find the `Job` dataclass. Add `job_class: JobClass = JobClass.NORMAL` and `mode: str = "normal"` after `seq: int = 0`.
verify: `python -c "import sys; sys.path.insert(0,'Code'); import batch.server as s; print(hasattr(s.Job,'job_class'))"`
expect: True
if_fail: Open `Code/batch/server.py`. Find the `class Job:` block. Add the two fields. Add the two imports at the top. Run `verify:` again.
result: True

### T002: Replace the worker with class queues
status: DONE
blocked_reason:
file: Code/batch/server.py
context: One priority queue per class. No mixed batch. Busy cap while call sessions are active.
do:
- [x] 1. EDIT `Code/batch/server.py`: replace the `BatchWorker` constructor, `submit`, and `_run` with class queues and `_collect`.
- [x] 2. EDIT `Code/batch/server.py`: add `enter_call`, `exit_call`, and `reload_config`.
- [x] 3. EDIT `Code/batch/server.py`: record `call_first_ms` and `call_first_wait_ms` for `CALL_FIRST` jobs.
verify: `python -c "import sys; sys.path.insert(0,'Code'); import batch.server as s; print(hasattr(s.BatchWorker,'enter_call') and hasattr(s.BatchWorker,'_collect'))"`
expect: True
if_fail: Open `Code/batch/server.py`. Find `class BatchWorker:`. Make the class match `Skeletons/Code/batch/server.py` revision 10 contract. Run `verify:` again.
result: True

### T003: Add the WebSocket call endpoint
status: DONE
blocked_reason:
file: Code/batch/server.py
context: Add `/ws/tts` with start, text, flush, and cancel. Use the call chunker and the call job classes.
do:
- [x] 1. EDIT `Code/batch/server.py`: add `app.state.chunk_cache = ChunkCache()` in `create_app`.
- [x] 2. EDIT `Code/batch/server.py`: add the `@app.websocket("/ws/tts")` handler before `@app.get("/debug/vram")`.
verify: `python -c "import sys; sys.path.insert(0,'Code'); from batch.server import create_app; a=create_app(start_engine=False); print(any(getattr(r,'path',None)=='/ws/tts' for r in a.routes))"`
expect: True
if_fail: Open `Code/batch/server.py`. Find `@app.get("/debug/vram")`. Add the WebSocket handler above it. Run `verify:` again.
result: True

### T004: Add the WebSocket check
status: DONE
blocked_reason:
file: Code/probes/check_call_ws.py
context: Use a fake engine and a TestClient. Prove start, chunk_start, PCM bytes, chunk_done, cancel, and session close.
do:
- [x] 1. CREATE `Code/probes/check_call_ws.py` with a fake engine and the WebSocket test.
- [x] 2. RUN the check.
verify: `python Code/probes/check_call_ws.py`
expect: {"ok": true}
if_fail: Open `Code/probes/out/check_call_ws.json`. Find the false field. Fix the server or the fake engine for that field. Run `verify:` again.
result: {"ok": true}

### T005: Prove normal HTTP did not regress
status: DONE
blocked_reason:
file: Code/probes/check_server.py
context: Run the existing serving check. It uses a fake engine and no GPU.
do:
- [x] 1. RUN `Code/probes/check_server.py`.
verify: `python Code/probes/check_server.py`
expect: {"ok": true}
if_fail: Open `Code/probes/out/check_server.json`. Find the false field. Fix `Code/batch/server.py` for that field. Run `verify:` again.
result: {"ok": true}
