<!-- ss-living-doc v1 -->
# SSLD-021: Call-mode server complete

## STATE
doc_id: SSLD-021
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: Skeletons/Code/batch/server.py
spec_revision: 10
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-021-call-mode-server-complete.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-021-call-mode-server-complete.md --sync

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

### T001: Route mode=call in HTTP stream
status: DONE
blocked_reason:
file: Code/batch/server.py
context: Route `POST /tts/stream?mode=call` to call chunking and call job classes.
do:
- [x] 1. EDIT `Code/batch/server.py`: in `/tts/stream`, detect `mode=call` and split text with `call_chunker`.
- [x] 2. EDIT `Code/batch/server.py`: submit the first chunk as `CALL_FIRST` and later chunks as `CALL_CONT`.
verify: `python Code/probes/check_call_ws.py`
expect: {"ok": true}
if_fail: Open `Code/batch/server.py`. Find `tts_stream`. Add `mode=call` chunking and class submit. Run `verify:` again.
result: {"ok": true}

### T002: Add class metrics
status: DONE
blocked_reason:
file: Code/batch/server.py
context: Add per-class first chunk metrics and wait behind normal.
do:
- [x] 1. EDIT `Code/batch/server.py`: record `first_chunk_ms_by_class` and `call_first_wait_behind_normal_ms`.
- [x] 2. EDIT `Code/batch/server.py`: add them to the metrics snapshot.
verify: `python Code/probes/check_call_ws.py`
expect: {"ok": true}
if_fail: Open `Code/batch/server.py`. Find `Metrics`. Add the fields and the snapshot keys. Run `verify:` again.
result: {"ok": true}

### T003: Close flush and add debug routes
status: DONE
blocked_reason:
file: Code/batch/server.py
context: Close the WebSocket after flush. Add debug routes for probes.
do:
- [x] 1. EDIT `Code/batch/server.py`: after `flush`, send `flushed`, close the socket, and return.
- [x] 2. EDIT `Code/batch/server.py`: add `/debug/callramp`, `/debug/callmixed`, and `/debug/callcancel` when `ARSENAL_DEBUG=1`.
verify: `python Code/probes/check_call_ws.py`
expect: {"ok": true}
if_fail: Open `Code/batch/server.py`. Find the `flush` branch and the debug route section. Fix the routes and close. Run `verify:` again.
result: {"ok": true}

### T004: Extend the call check
status: DONE
blocked_reason:
file: Code/probes/check_call_ws.py
context: Prove flush close, `mode=call` stream, and debug routes.
do:
- [x] 1. EDIT `Code/probes/check_call_ws.py`: add a flush test, a `mode=call` stream test, and debug route tests.
- [x] 2. RUN the check.
verify: `python Code/probes/check_call_ws.py`
expect: {"ok": true}
if_fail: Open `Code/probes/out/check_call_ws.json`. Find the false field. Fix the server or the check. Run `verify:` again.
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
if_fail: Open `Code/probes/out/check_server.json`. Find the false field. Fix `Code/batch/server.py`. Run `verify:` again.
result: {"ok": true}
