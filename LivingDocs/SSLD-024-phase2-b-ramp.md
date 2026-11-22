<!-- ss-living-doc v1 -->
# SSLD-024: Phase 2 B-ramp - sentence vs utterance

## STATE
doc_id: SSLD-024
status: DONE
current_task: T003
tasks_done: 3
tasks_total: 3
skeleton: Skeletons/Code/batch/server.py
spec_revision: 11
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-024-phase2-b-ramp.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-024-phase2-b-ramp.md --sync

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

- Goal: high B, low latency, best natural quality.
- Double-assure: test `sentence` and `utterance`, raw quality modes.
- Use debug callramp, first_only=1, short text.

## TASKS

### T001: Smoke callramp mode support

status: DONE
blocked_reason:
file: Code/probes/probe_phase2_bramp.py
context: Create a small probe that starts server, runs smoke B=4 for sentence and utterance, writes JSON.
do:
- [x] 1. CREATE `Code/probes/probe_phase2_bramp.py` with smoke + ramp support.
- [x] 2. RUN `python -m py_compile Code/probes/probe_phase2_bramp.py`.
verify: `python -m py_compile Code/probes/probe_phase2_bramp.py`
expect: exit code 0
if_fail: Fix syntax and run verify again.
result: exit code 0

### T002: Run B-ramp

status: DONE
blocked_reason:
file: Code/probes/out/phase2_bramp/
also_edit: Code/probes/probe_phase2_bramp.py
context: Run B=32,64,96,128,224,320,448 for sentence and utterance, first_only=1, 3 reps. Save JSON.
do:
- [x] 1. RUN `timeout 1800 python Code/probes/probe_phase2_bramp.py --mode both --out Code/probes/out/phase2_bramp/ramp.json`.
- [x] 2. CHECK JSON has rows for both modes and B values.
verify: `python -c "import json; d=json.load(open('Code/probes/out/phase2_bramp/ramp.json')); print(len(d['rows']), sorted({r['mode'] for r in d['rows']}))"`
expect: 14 ['sentence', 'utterance']
if_fail: Check server log and rerun once.
result: 14 ['sentence', 'utterance']

### T003: Record StageSet evidence

status: DONE
blocked_reason:
file: Ideas/IDEA-0008-natural-live-call-streaming.md
also_edit: .stageset/facts.md
context: Add run report, FACT, IDEA update, session event, sync.
do:
- [x] 1. CREATE run report and FACT from ramp JSON.
- [x] 2. EDIT IDEA-0008 with Phase 2 result and update metadata.
- [x] 3. RUN `python scripts/stageset-status.py --sync && python scripts/stageset-status.py --validate`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Fix validation error and rerun.
result: StageSet validation passed.
