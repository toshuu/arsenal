<!-- ss-living-doc v1 -->
# SSLD-028: Phase 4 quiet formation at B=320

## STATE
doc_id: SSLD-028
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Probes/probe_phase4_quiet.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-028-phase4-quiet.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-028-phase4-quiet.md --sync

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

- FACT-0154: B=320 is one batch at cap 640, but p95 is 389 to 424 ms.
- The full 150 ms window wait is in that number because target was 640.
- Test a quiet policy with buckets off at B=320. This removes the target wait.
- A low target (64) is a control. It shows the split risk.
- This probe does not change app code.

## TASKS

### T001: Create the quiet probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_quiet.py
context: This probe starts one fresh server per policy and writes 48 rows. It uses B=320 only.
do:
- [x] 1. CREATE `Code/probes/probe_phase4_quiet.py` with the code block below.
- [x] 2. CHECK that the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/probe_phase4_quiet.py`.

   ```python
   """Phase 4 quiet formation probe at B=320, real uvicorn, fresh server per policy."""
   from __future__ import annotations
   import argparse, json, os, subprocess, sys, time
   from pathlib import Path
   import requests

   ROOT = Path(__file__).resolve().parents[2]
   REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
   PORT = int(os.getenv("ARSENAL_PHASE4_QUIET_PORT", "8126"))
   TEXT = "Hello, can you hear me clearly right now?"
   OUT = ROOT / "Code/probes/out/phase4_quiet"
   CAP = 640
   POLICIES = [
       {
           "name": "target64",
           "env": {
               "ARSENAL_BATCH_TARGET": "64",
               "ARSENAL_CALL_FIRST_QUIET_MS": "0",
               "ARSENAL_CALL_FIRST_HARD_CAP_MS": "0",
               "ARSENAL_CALL_FIRST_BUCKETS": "1",
           },
       },
       {
           "name": "q2h20_nb",
           "env": {
               "ARSENAL_BATCH_TARGET": "640",
               "ARSENAL_CALL_FIRST_QUIET_MS": "2",
               "ARSENAL_CALL_FIRST_HARD_CAP_MS": "20",
               "ARSENAL_CALL_FIRST_BUCKETS": "0",
           },
       },
       {
           "name": "q2h30_nb",
           "env": {
               "ARSENAL_BATCH_TARGET": "640",
               "ARSENAL_CALL_FIRST_QUIET_MS": "2",
               "ARSENAL_CALL_FIRST_HARD_CAP_MS": "30",
               "ARSENAL_CALL_FIRST_BUCKETS": "0",
           },
       },
       {
           "name": "q3h40_nb",
           "env": {
               "ARSENAL_BATCH_TARGET": "640",
               "ARSENAL_CALL_FIRST_QUIET_MS": "3",
               "ARSENAL_CALL_FIRST_HARD_CAP_MS": "40",
               "ARSENAL_CALL_FIRST_BUCKETS": "0",
           },
       },
   ]


   def base_env():
       env = os.environ.copy()
       env.update({
           "ARSENAL_PREWARM": "0",
           "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
           "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
           "ARSENAL_VOICE": str(REF),
           "ARSENAL_DEBUG": "1",
           "ARSENAL_MAX_QUEUE": "4096",
           "ARSENAL_MAX_ROWS": str(CAP),
           "ARSENAL_MAX_BATCH": str(CAP),
           "ARSENAL_CALL_FIRST_MAX_BATCH": str(CAP),
           "ARSENAL_CALL_FIRST_SUB_BATCH": str(CAP),
           "ARSENAL_BATCH_WINDOW_MS": "150",
       })
       return env


   def wait(base, timeout=300):
       end = time.time() + timeout
       while time.time() < end:
           try:
               response = requests.get(base + "/health", timeout=2)
               if response.ok and response.json().get("ready"):
                   return
           except Exception:
               pass
           time.sleep(1)
       raise RuntimeError("server not ready")


   def run_policy(policy, calls, port):
       env = base_env()
       env.update(policy["env"])
       log = (OUT / ("server_%s.log" % policy["name"])).open("w")
       proc = subprocess.Popen(
           [sys.executable, "-m", "uvicorn", "batch.server:app",
            "--host", "127.0.0.1", "--port", str(port)],
           cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT,
       )
       rows = []
       try:
           base = "http://127.0.0.1:%d" % port
           wait(base)
           for mode in ["sentence", "utterance"]:
               for call in range(calls):
                   params = {
                       "b": 320, "repeats": 1, "first_only": 1,
                       "stream_mode": mode, "first_max_frames": 8,
                       "text": TEXT,
                   }
                   response = requests.get(
                       base + "/debug/callramp", params=params, timeout=600
                   )
                   response.raise_for_status()
                   run = response.json()["runs"][0]
                   first = run.get("first_byte_ms") or {}
                   row = {
                       "policy": policy["name"], "mode": mode, "call": call,
                       "warm": call > 1,
                       "p50": first.get("p50"), "p95": first.get("p95"),
                       "errors": run.get("errors"),
                       "batch_sizes": run.get("batch_sizes"),
                       "vram_after": (run.get("vram_mb") or {}).get("after"),
                   }
                   rows.append(row)
                   print(json.dumps(row), flush=True)
       finally:
           proc.terminate()
           try:
               proc.wait(timeout=20)
           except Exception:
               proc.kill()
           log.close()
       return rows


   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--calls", type=int, default=6)
       parser.add_argument("--out", type=Path, default=OUT / "quiet.json")
       args = parser.parse_args()
       args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
       OUT.mkdir(parents=True, exist_ok=True)
       all_rows = []
       for index, policy in enumerate(POLICIES):
           rows = run_policy(policy, args.calls, PORT + index)
           all_rows.extend(rows)
           data = {"ok": True, "policies": POLICIES, "rows": all_rows}
           args.out.write_text(json.dumps(data, indent=2))
       data = {"ok": True, "policies": POLICIES, "rows": all_rows}
       args.out.write_text(json.dumps(data, indent=2))
       print(json.dumps({"ok": True, "rows": len(all_rows)}))


   if __name__ == "__main__":
       main()
   ```
verify: `python -m py_compile Code/probes/probe_phase4_quiet.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_phase4_quiet.py`. Compare the file to the code block in step 1. Run `verify:` again.
result: exit:0

### T002: Run the quiet probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_quiet.py
also_edit: Code/probes/out/phase4_quiet/
context: Run 48 callramp calls. 4 policies. B=320 only. Fresh server per policy. The T4 must be free.
do:
- [x] 1. RUN `timeout 2400 python Code/probes/probe_phase4_quiet.py`.
- [x] 2. CHECK that the command prints one final JSON line with `"rows": 48`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/phase4_quiet/quiet.json')); print(len(d['rows']), len(d['policies']))"`
expect: 48 4
if_fail: Run `nvidia-smi` and check free memory. Run the probe again. If it still fails, set status BLOCKED and write the failing output in blocked_reason.
result: 48 4
### T003: Create the run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-195737-RUN.md
context: The probe JSON exists. Write the PROBE run report with this exact id. Use values from the JSON. Do not invent values.
do:
- [x] 1. CREATE `.stageset/runs/20261122-195737-RUN.md` with the block below.
- [x] 2. EDIT the block: replace `<RESULT>`, `<PASS_TABLE>`, and `<FLOOR>` with values from `Code/probes/out/phase4_quiet/quiet.json`.
- [x] 3. CHECK that no file in `.stageset/runs/` ends with `.reserve`.

   ```markdown
   ---
   id: 20261122-195737-RUN
   type: PROBE
   time: 2026-11-22T19:57:37+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_phase4_quiet.md
   check_id: CHECK-PHASE4-QUIET-02
   attempt: 1
   spec_revision: 1
   command: "python Code/probes/probe_phase4_quiet.py"
   ---

   # Run report

   ## Goal

   Test if a quiet policy with buckets off meets the 350 ms gate at B=320 on a real server.

   ## Commands

   ```text
   python Code/probes/probe_phase4_quiet.py
   ```

   ## Observed output (trimmed)

   Full rows are in `Code/probes/out/phase4_quiet/quiet.json`. Trimmed: only the policy pass table is shown here.

   Policy pass table `(all one batch, worst warm p95)`: <PASS_TABLE>.

   Floor: <FLOOR>.

   ## Result

   <RESULT>

   ## Facts

   Policy pass table: <PASS_TABLE>. Floor: <FLOOR>. All rows have `batch_sizes`.

   ## Guesses

   None.

   ## Assumptions checked

   A-53: the pass table. A-54: `<FLOOR>` has no OOM and no error.

   ## Tried

   4 server starts. 48 callramp calls.

   ## Open question for planner

   Does a policy pass at B=320, or is it the floor?

   ## Attempt diff

   First attempt. This probe removes the target wait with a quiet policy.

   ## Smallest repro

   `python Code/probes/probe_phase4_quiet.py`
   ```
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix only the named run report field. Run `verify:` again.
result: StageSet validation passed.
### T004: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-phase4-quiet.md
context: The probe ran and the run report exists. Record one CODING event for this session.
do:
- [x] 1. CREATE `.stageset/sessions/coding-phase4-quiet.md` with the block below.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the event `time` or `type` value. Run `verify:` again.
result: StageSet validation passed.
   ```markdown
   ---
   type: CODING
   time: 2026-11-22T19:57:37+05:30
   summary: Run the Phase 4 quiet formation probe at B=320.
   paths: Code/probes/probe_phase4_quiet.py; Code/probes/out/phase4_quiet/quiet.json; .stageset/runs/20261122-195737-RUN.md; Skeletons/Probes/probe_phase4_quiet.md
   related: IDEA-0008; SSLD-028; FACT-0154; 20261122-195737-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Test 4 formation policies at B=320 with buckets on and off.

   ## Outcomes

   - The probe ran. The measured values are in `20261122-195737-RUN`.

   ## Follow-up

   - The planner reads the run report and picks the policy or the floor.
   ```

### T005: Update the probe metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_phase4_quiet.md
context: The probe ran and the evidence exists. Record that the probe implements revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_phase4_quiet.md`: find line `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_phase4_quiet.md`: find line `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_phase4_quiet.md`: find line `@stageset implemented_in: -` and replace it with `@stageset implemented_in: .stageset/sessions/coding-phase4-quiet.md`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_phase4_quiet.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)',s).group(1), re.search(r'@stageset status: (\w+)',s).group(1))"`
expect: 1 DONE
if_fail: Open `Skeletons/Probes/probe_phase4_quiet.md`. Fix the three metadata lines. Run `verify:` again.
result: 1 DONE
### T006: Sync and validate
status: DONE
blocked_reason:
file: .stageset/DIGEST.md
context: All evidence files exist. Rebuild the tracker and digest. Run the validator.
do:
- [x] 1. RUN `python scripts/stageset-status.py --sync`.
- [x] 2. RUN `python scripts/stageset-status.py --validate`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the named file. Run `verify:` again.
result: StageSet validation passed.
