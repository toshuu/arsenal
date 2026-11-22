<!-- ss-living-doc v1 -->
# SSLD-023: Server quality modes - Phase 1

## STATE
doc_id: SSLD-023
status: DONE
current_task: T004
tasks_done: 4
tasks_total: 4
skeleton: Skeletons/Code/batch/server.py
spec_revision: 11
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-023-server-quality-modes.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-023-server-quality-modes.md --sync

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

## STRATEGY

- Add three WS modes: `sentence`, `utterance`, `latency`.
- Default is `ARSENAL_CALL_STREAM_MODE` or `sentence`.
- Quality modes skip pause compression and use mode-specific BatchedStream settings.
- `latency` keeps the legacy 16-token cut and pause compression.
- HTTP `/tts/stream?mode=call` is unchanged in this phase.
- Listen result FACT-0148 says `sentence` and `utterance` match by ear.

## TASKS

### T001: Add mode helpers and a CPU check

status: DONE
blocked_reason:
file: Code/batch/server.py
also_edit: Code/probes/check_server_modes.py
context: Add small pure helpers. The check must run without a GPU.
do:
- [x] 1. EDIT `Code/batch/server.py`: add `CALL_STREAM_MODES`, `CALL_STREAM_SETTINGS`, `resolve_call_stream_mode(value=None)`, and `quality_stream_raw(mode)`.
- [x] 2. CREATE `Code/probes/check_server_modes.py` to check default, explicit modes, unknown rejection, and raw-frame flags.
verify: `python Code/probes/check_server_modes.py`
expect: {"ok": true}
if_fail: Read the check output. Fix only the helper or the check. Run verify again.
result: {"ok": true}

### T002: Route generation through the selected mode

status: DONE
blocked_reason:
file: Code/batch/server.py
context: Carry the mode from a job to the engine. Create cached mode streams with the right BatchedStream settings.
do:
- [x] 1. EDIT `Job`: add `stream_mode: str = "normal"`.
- [x] 2. EDIT `worker.submit`: add `stream_mode: str = "normal"` and set it on the job.
- [x] 3. EDIT `_execute_group`: pass one shared `stream_mode` to `engine.synthesize`.
- [x] 4. EDIT `TTSEngine`: add `_mode_stream(profile_id, mode)` and use it in `synthesize` for quality modes.
verify: `python -m py_compile Code/batch/server.py`
expect: exit code 0
if_fail: Fix the syntax error and run verify again.
result: exit code 0

### T003: Wire the WebSocket path

status: DONE
blocked_reason:
file: Code/batch/server.py
also_edit: Code/probes/check_call_ws.py
context: Use the mode from `start`. Pick chunks and frame caps by mode. Only `latency` keeps pause compression.
do:
- [x] 1. EDIT the `start` handler: resolve `stream_mode` or `mode`. Reject unknown values and keep the session open.
- [x] 2. EDIT the `text` handler: use `utterance` as one chunk, `sentence` via `_text_chunks`, and `latency` via `split_call_text`.
- [x] 3. EDIT each submit call: add `stream_mode=mode`. Add `stream_mode` to `chunk_start` and `utterance_done`.
- [x] 4. EDIT the frame send block: skip `StreamPauseCompressor` for quality modes. Keep it for `latency`.
verify: `python Code/probes/check_call_ws.py`
expect: {"ok": true}
if_fail: Fix only the WS path. Run verify again.
result: {"ok": true}

### T004: Finish metadata

status: DONE
blocked_reason:
file: Skeletons/Code/batch/server.py
also_edit: Ideas/IDEA-0008-natural-live-call-streaming.md
context: All checks pass. Mark the server skeleton as implemented at revision 11.
do:
- [x] 1. EDIT `Skeletons/Code/batch/server.py`: `implemented_revision: 10` -> `11`, `status: READY` -> `DONE`, `implemented_in: .stageset/sessions/coding-ssld-022-listen-gate.md` -> the new coding event path.
- [x] 2. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: add SSLD-023 to `related_skeletons`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Code/batch/server.py').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)',s).group(1), re.search(r'@stageset status: (\w+)',s).group(1))"`
expect: 11 DONE
if_fail: Fix the metadata and run verify again.
result: 11 DONE
