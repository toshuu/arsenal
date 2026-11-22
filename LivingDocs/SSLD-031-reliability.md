<!-- ss-living-doc v1 -->
# SSLD-031: Restore measurement integrity and re-run the WS gate

## STATE
doc_id: SSLD-031
status: BLOCKED
current_task: T004
tasks_done: 3
tasks_total: 10
skeleton: Skeletons/Probes/probe_ws_burst_gate.md
spec_revision: 2
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-031-reliability.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-031-reliability.md --sync

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

The SSLD-030 result is not valid. The executor edited the shared burst client
and added JSON fields that the probe does not produce. The FAIL is a
measurement fault, not a server result.

This document does five things:

1. Preserve the deviated files. Do not use them.
2. Restore `Code/probes/call_load_client.py` to HEAD. HEAD uses one
   pre-connected client set, drains before each repetition, and excludes
   warmups. This is the method behind FACT-0139.
3. Bind `gate.json` to the probe script and the client with SHA-256.
4. Re-run B=224 and B=320 with `sentence`.
5. Write a corrected run report and update the idea and facts.

Do not tune the collector. Do not change app code.

## TASKS

### T001: Preserve the deviated evidence
status: DONE
blocked_reason:
file: Code/probes/out/ws_burst_gate/deviated/
context: Keep the edited client and the suspect JSON. These files are evidence. Do not use them for a result.
do:
- [x] 1. RUN `mkdir -p Code/probes/out/ws_burst_gate/deviated`.
- [x] 2. COPY `Code/probes/call_load_client.py` to `Code/probes/out/ws_burst_gate/deviated/call_load_client_deviated.py`.
- [x] 3. COPY `Code/probes/out/ws_burst_gate/gate.json` to `Code/probes/out/ws_burst_gate/deviated/gate_deviated.json`.
- [x] 4. COPY `Code/probes/out/ws_burst_gate/burst_224.json` to `Code/probes/out/ws_burst_gate/deviated/burst_224_deviated.json`.
- [x] 5. COPY `Code/probes/out/ws_burst_gate/burst_320.json` to `Code/probes/out/ws_burst_gate/deviated/burst_320_deviated.json`.
verify: `ls Code/probes/out/ws_burst_gate/deviated | wc -l`
expect: 4
if_fail: If one source file is missing, skip only that copy. Run the other copies again. Run `verify:` and expect a count of at least 2.
result: 4

### T002: Restore the burst client
status: DONE
blocked_reason:
file: Code/probes/call_load_client.py
context: The executor edited this shared client during SSLD-030. Restore the HEAD version. The deviated copy is in the evidence folder.
do:
- [x] 1. RUN `git checkout -- Code/probes/call_load_client.py`.
- [x] 2. CHECK that `git diff --quiet -- Code/probes/call_load_client.py` exits with 0.
verify: `python -c "import subprocess; print(subprocess.run(['git','diff','--quiet','--','Code/probes/call_load_client.py']).returncode)"`
expect: 0
if_fail: RUN `git checkout -- Code/probes/call_load_client.py` again. Run `verify:` again. If it is not 0, set status BLOCKED.
result: 0

### T003: Add SHA-256 provenance to the probe
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
context: The probe must write the hashes of its own file and the client file. This stops edited or invented output.
do:
- [x] 1. EDIT `Code/probes/probe_ws_burst_gate.py`: find the line `import json` and replace it with `import hashlib` then a new line `import json`.
- [x] 2. EDIT `Code/probes/probe_ws_burst_gate.py`: find the two lines `        "ok": True,` and `        "gate_224": gate,` and replace them with the four lines in the code block below.
- [x] 3. RUN `python -m py_compile Code/probes/probe_ws_burst_gate.py`.

   ```python
           "ok": True,
           "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "client_sha256": hashlib.sha256((ROOT / "Code/probes/call_load_client.py").read_bytes()).hexdigest(),
           "gate_224": gate,
   ```
verify: `python -m py_compile Code/probes/probe_ws_burst_gate.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_ws_burst_gate.py`. Check the `import hashlib` line and the four lines in the `out` dict. Run `verify:` again.
result: exit code 0

### T004: Re-run the WS burst gate
status: BLOCKED
blocked_reason: HEAD client holds 224 WS sessions open. active_call_sessions stays at 224. drain() waits its full 120 s timeout twice per rep. Six reps per B need about 22 min. Two B values need about 45 min. This exceeds the 2400 s probe timeout. Observed: first burst ended at 2:32 elapsed with completed=224. No second burst at 5:30 elapsed. Planner must revise the client method or the time budget.
file: Code/probes/probe_ws_burst_gate.py
also_edit: Code/probes/out/ws_burst_gate/
context: The T4 must be free. Delete the three old result files first. The probe starts one fresh server and writes new files.
do:
- [x] 1. RUN `rm -f Code/probes/out/ws_burst_gate/gate.json Code/probes/out/ws_burst_gate/burst_224.json Code/probes/out/ws_burst_gate/burst_320.json`.
- [x] 2. RUN `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader`.
- [x] 3. RUN `timeout 2400 python Code/probes/probe_ws_burst_gate.py`.
- [ ] 4. CHECK that the final line is JSON with the key `gate_224`.
verify: `python -c "import json,hashlib,pathlib; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); p=pathlib.Path('Code/probes/probe_ws_burst_gate.py'); c=pathlib.Path('Code/probes/call_load_client.py'); print(len(d['rows']), d['probe_sha256']==hashlib.sha256(p.read_bytes()).hexdigest(), d['client_sha256']==hashlib.sha256(c.read_bytes()).hexdigest(), 'per_rep' not in d['rows'][0])"`
expect: 2 True True True
if_fail: Run `nvidia-smi`. Stop other GPU work. Run steps 1 and 3 again. If it fails again, set status BLOCKED and write the error in blocked_reason.
result:

### T005: Create the corrected run report
status: TODO
blocked_reason:
file: .stageset/runs/20261122-220000-RUN.md
context: This is attempt 2. Use the real values from gate.json. Do not invent values. State that attempt 1 is deviated.
do:
- [ ] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors']} for r in d['rows']})"`.
- [ ] 2. CREATE `.stageset/runs/20261122-220000-RUN.md` with the block below.
- [ ] 3. EDIT `.stageset/runs/20261122-220000-RUN.md`: replace `<TABLE>` with the output of step 1.
- [ ] 4. EDIT `.stageset/runs/20261122-220000-RUN.md`: replace `<RESULT>` with `PASS` if the 224 entry has `errors` 0 and `p95` <= 350. Else replace it with `FAIL`.
- [ ] 5. CHECK that no file in `.stageset/runs/` ends with `.reserve`.

   ```markdown
   ---
   id: 20261122-220000-RUN
   type: PROBE
   time: 2026-11-22T22:00:00+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_ws_burst_gate.md
   check_id: CHECK-WS-GATE-02
   attempt: 2
   spec_revision: 2
   command: "python Code/probes/probe_ws_burst_gate.py"
   ---

   # Run report

   ## Goal

   Prove the first-sound gate on the real WebSocket path at the default call config. This is attempt 2. Attempt 1 (`20261122-210000-RUN`) is deviated. The SSLD-030 executor edited the shared burst client and added fields that the probe does not write. Attempt 1 is not used.

   ## Commands

   ```text
   git checkout -- Code/probes/call_load_client.py
   python Code/probes/probe_ws_burst_gate.py
   ```

   ## Observed output (trimmed)

   Full rows: `Code/probes/out/ws_burst_gate/gate.json`. Gate table: <TABLE>.

   The output has `probe_sha256` and `client_sha256`. Both match the files on disk. The client is the HEAD version. Warmups are excluded. The server starts once per B run.

   ## Result

   <RESULT>

   ## Facts

   Gate table: <TABLE>. The client pre-connects and starts each WS before the barrier. The clock starts at text send and stops at the first audio byte. Warmup rows are not in the p95.

   ## Guesses

   None.

   ## Assumptions checked

   - The HEAD burst client keeps one pre-connected set and drains before each repetition.
   - `sentence` sends raw frames with no pause compression.

   ## Tried

   One fresh server. Two B values. 2 warmups and 4 measured burst repetitions per B.

   ## Open question for planner

   Is B=224 `sentence` a stable end-to-end operating point? Does B=320 stay above 350 ms?

   ## Attempt diff

   Attempt 2 restores the HEAD client and adds SHA-256 provenance. No app code change.

   ## Smallest repro

   `python Code/probes/probe_ws_burst_gate.py`
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/runs/20261122-220000-RUN.md').read_text(); print('<RESULT>' not in s, '<TABLE>' not in s, 'attempt: 2' in s)"`
expect: True True True
if_fail: Open the run report. Replace `<RESULT>` and `<TABLE>`. Run `verify:` again.
result:

### T006: Create the coding event
status: TODO
blocked_reason:
file: .stageset/sessions/coding-ssld-031-reliability.md
context: Record one CODING event for the corrected probe run. Use the real current time.
do:
- [ ] 1. RUN `date +%Y-%m-%dT%H:%M:%S%:z`.
- [ ] 2. CREATE `.stageset/sessions/coding-ssld-031-reliability.md` with the block below.
- [ ] 3. EDIT `.stageset/sessions/coding-ssld-031-reliability.md`: replace `<TIME>` with the output of step 1.

   ```markdown
   ---
   type: CODING
   time: <TIME>
   summary: Restore the burst client and re-run the real WS gate.
   paths: Code/probes/call_load_client.py; Code/probes/probe_ws_burst_gate.py; Code/probes/out/ws_burst_gate/gate.json; .stageset/runs/20261122-220000-RUN.md; Skeletons/Probes/probe_ws_burst_gate.md
   related: IDEA-0008; SSLD-030; SSLD-031; 20261122-220000-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Restore the HEAD burst client.
   - Use SHA-256 provenance for the probe output.

   ## Outcomes

   - The corrected gate table is in `20261122-220000-RUN`.

   ## Follow-up

   - Planner locks B=224 if the gate passes. Inspect the phase gap if it fails.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/sessions/coding-ssld-031-reliability.md').read_text(); print('<TIME>' not in s, 'type: CODING' in s)"`
expect: True True
if_fail: Open the event. Replace `<TIME>` with the real time. Run `verify:` again.
result:

### T007: Update the probe skeleton metadata
status: TODO
blocked_reason:
file: Skeletons/Probes/probe_ws_burst_gate.md
context: The probe now implements revision 2. The corrected run resolves the block.
do:
- [ ] 1. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset implemented_revision: 1` and replace it with `@stageset implemented_revision: 2`.
- [ ] 2. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [ ] 3. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset implemented_in: .stageset/sessions/coding-ssld-030-ws-burst-gate.md` and replace it with `@stageset implemented_in: .stageset/sessions/coding-ssld-031-reliability.md`.
- [ ] 4. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset resolution_of: -` and replace it with `@stageset resolution_of: 20261122-220000-RUN`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_ws_burst_gate.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)', s).group(1), re.search(r'@stageset status: (\w+)', s).group(1), re.search(r'@stageset resolution_of: (\S+)', s).group(1))"`
expect: 2 DONE 20261122-220000-RUN
if_fail: Open the skeleton. Fix the four metadata lines. Run `verify:` again.
result:

### T008: Correct the idea record
status: TODO
blocked_reason:
file: Ideas/IDEA-0008-natural-live-call-streaming.md
context: The old Phase 5 section uses the deviated data. Mark it. Append a corrected section with the real values.
do:
- [ ] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors']} for r in d['rows']})"`.
- [ ] 2. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: find `## Phase 5 WS gate` and replace it with `## Phase 5 WS gate (deviated attempt)`.
- [ ] 3. APPEND to `Ideas/IDEA-0008-natural-live-call-streaming.md` the block below.
- [ ] 4. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<TABLE>` with the output of step 1.
- [ ] 5. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<DECISION>` with `B=224 sentence is the locked operating point.` if the 224 entry has `errors` 0 and `p95` <= 350. Else replace it with `B=224 sentence is not yet locked. Inspect the phase gap.`.

   ```markdown

   ## Phase 5 WS gate (corrected)

   `20261122-220000-RUN` is the valid attempt. It uses the HEAD burst client and
   SHA-256 provenance. The prior attempt edited the shared client and is not used.
   Table: <TABLE>.

   Decision: <DECISION>

   B=320 stays a measurement point. Do not set it as a target without a new
   formation or admission change.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('Ideas/IDEA-0008-natural-live-call-streaming.md').read_text(); print(s.count('## Phase 5 WS gate (corrected)'), '<DECISION>' not in s, '<TABLE>' not in s)"`
expect: 1 True True
if_fail: Open the idea file. Fix the heading, the table, or the decision. Run `verify:` again.
result:

### T009: Record the corrected fact
status: TODO
blocked_reason:
file: .stageset/facts.md
context: Add one fact row from the corrected run. Use the real values. Do not change old rows.
do:
- [ ] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print('; '.join('%d ms p50 %.2f p95 %.2f errors %d' % (r['b'], r['p50_of_p50'], r['p95_of_p95'], r['errors']) for r in d['rows']))"`.
- [ ] 2. APPEND to `.stageset/facts.md` the row below.
- [ ] 3. EDIT `.stageset/facts.md`: replace `<TABLE>` with the output of step 1.

   ```markdown
   | FACT-0157 | 2026-11-22 | Real WS burst gate, HEAD client, one pre-connected set, 2 warmups and 4 measured reps, `sentence` raw frames, default `BATCH_TARGET=32`, SHA-256 bound output: <TABLE>. Attempt 1 (`20261122-210000-RUN`) is deviated and not used. | Project | CURRENT | `.stageset/runs/20261122-220000-RUN.md` |
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/facts.md').read_text(); print(s.count('FACT-0157'), '<TABLE>' not in s)"`
expect: 1 True
if_fail: Open `facts.md`. Fix the FACT-0157 row and the `<TABLE>` value. Run `verify:` again.
result:

### T010: Sync and validate
status: TODO
blocked_reason:
file: .stageset/DIGEST.md
context: All evidence files exist. Rebuild the tracker and digest. Run the validator.
do:
- [ ] 1. RUN `python scripts/stageset-status.py --sync`.
- [ ] 2. RUN `python scripts/stageset-status.py --validate`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the named file. Run `verify:` again.
result:
