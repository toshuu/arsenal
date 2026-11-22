<!-- ss-living-doc v1 -->
# SSLD-029: Phase 4 quiet early-break fix

## STATE
doc_id: SSLD-029
status: DONE
current_task: T007
tasks_done: 7
tasks_total: 7
skeleton: Skeletons/Probes/probe_phase4_quiet_fix.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-029-phase4-quiet-fix.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-029-phase4-quiet-fix.md --sync

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

- FACT-0155: quiet policies split `[1,319]`. Cause: early break on `active_call_sessions`.
- Fix: require `len(batch) >= min_early` before the early break. Default 32.
- Then run a real B=320 probe with `q2h30_nb` and `q3h40_nb`.

## TASKS

### T001: Guard the quiet early break
status: DONE
blocked_reason:
file: Code/batch/server.py
context: `_collect_call_first_quiet` breaks too early when `active_call_sessions` is 1. Add a minimum batch size guard.
do:
- [x] 1. EDIT `Code/batch/server.py`: find the line `            if self.active_call_sessions > 0 and len(batch) >= self.active_call_sessions:` and replace it with `            min_early = int(os.getenv("ARSENAL_CALL_FIRST_MIN_EARLY", "32"))`.
- [x] 2. EDIT `Code/batch/server.py`: find the next line `                break` that is directly under that guard and replace it with `            if self.active_call_sessions > 0 and len(batch) >= max(self.active_call_sessions, min_early):\n                break`.
- [x] 3. RUN `python -m py_compile Code/batch/server.py`.
verify: `python -m py_compile Code/batch/server.py`
expect: exit code 0
if_fail: Open `Code/batch/server.py`. Check the two edited lines around the quiet early break. Run `verify:` again.
result: exit code 0
### T002: Create the fix probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_quiet_fix.py
context: Real uvicorn, fresh server per policy, B=320, 2 policies, 24 rows.
do:
- [x] 1. CREATE `Code/probes/probe_phase4_quiet_fix.py` with the code block below.
- [x] 2. RUN `python -m py_compile Code/probes/probe_phase4_quiet_fix.py`.

   ```python
   """Phase 4 quiet fix probe at B=320."""
   from __future__ import annotations
   import argparse, json, os, subprocess, sys, time
   from pathlib import Path
   import requests

   ROOT = Path(__file__).resolve().parents[2]
   REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
   PORT = int(os.getenv("ARSENAL_PHASE4_QUIET_FIX_PORT", "8130"))
   TEXT = "Hello, can you hear me clearly right now?"
   OUT = ROOT / "Code/probes/out/phase4_quiet_fix"
   CAP = 640
   POLICIES = [
       {"name": "q2h30_nb", "env": {"ARSENAL_BATCH_TARGET": "640", "ARSENAL_CALL_FIRST_QUIET_MS": "2", "ARSENAL_CALL_FIRST_HARD_CAP_MS": "30", "ARSENAL_CALL_FIRST_BUCKETS": "0", "ARSENAL_CALL_FIRST_MIN_EARLY": "32"}},
       {"name": "q3h40_nb", "env": {"ARSENAL_BATCH_TARGET": "640", "ARSENAL_CALL_FIRST_QUIET_MS": "3", "ARSENAL_CALL_FIRST_HARD_CAP_MS": "40", "ARSENAL_CALL_FIRST_BUCKETS": "0", "ARSENAL_CALL_FIRST_MIN_EARLY": "32"}},
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
           cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT)
       rows = []
       try:
           base = "http://127.0.0.1:%d" % port
           wait(base)
           for mode in ["sentence", "utterance"]:
               for call in range(calls):
                   params = {"b": 320, "repeats": 1, "first_only": 1, "stream_mode": mode, "first_max_frames": 8, "text": TEXT}
                   response = requests.get(base + "/debug/callramp", params=params, timeout=600)
                   response.raise_for_status()
                   run = response.json()["runs"][0]
                   first = run.get("first_byte_ms") or {}
                   row = {"policy": policy["name"], "mode": mode, "call": call, "warm": call > 1,
                          "p50": first.get("p50"), "p95": first.get("p95"), "errors": run.get("errors"),
                          "batch_sizes": run.get("batch_sizes"), "vram_after": (run.get("vram_mb") or {}).get("after")}
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
       parser.add_argument("--out", type=Path, default=OUT / "fix.json")
       args = parser.parse_args()
       args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
       OUT.mkdir(parents=True, exist_ok=True)
       all_rows = []
       for index, policy in enumerate(POLICIES):
           rows = run_policy(policy, args.calls, PORT + index)
           all_rows.extend(rows)
           args.out.write_text(json.dumps({"ok": True, "policies": POLICIES, "rows": all_rows}, indent=2))
       args.out.write_text(json.dumps({"ok": True, "policies": POLICIES, "rows": all_rows}, indent=2))
       print(json.dumps({"ok": True, "rows": len(all_rows)}))


   if __name__ == "__main__":
       main()
   ```
verify: `python -m py_compile Code/probes/probe_phase4_quiet_fix.py`
expect: exit code 0
if_fail: Compare the file to the code block. Run `verify:` again.
result: exit code 0
### T003: Run the fix probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_quiet_fix.py
also_edit: Code/probes/out/phase4_quiet_fix/
context: 2 policies, B=320, 24 rows. T4 must be free.
do:
- [x] 1. RUN `timeout 1800 python Code/probes/probe_phase4_quiet_fix.py`.
- [x] 2. CHECK that the final JSON line has `"rows": 24`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/phase4_quiet_fix/fix.json')); print(len(d['rows']), len(d['policies']))"`
expect: 24 2
if_fail: Run `nvidia-smi`. Run the probe again. If it fails again, set BLOCKED.
result: 24 2
### T004: Create the run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-200804-RUN.md
context: Write the PROBE run report with measured values from `Code/probes/out/phase4_quiet_fix/fix.json`.
do:
- [x] 1. CREATE `.stageset/runs/20261122-200804-RUN.md` with the block below.
- [x] 2. EDIT `<RESULT>`, `<PASS_TABLE>`, `<FLOOR>` with values from the JSON.
- [x] 3. CHECK no `.reserve` file in `.stageset/runs/`.

   ```markdown
   ---
   id: 20261122-200804-RUN
   type: PROBE
   time: 2026-11-22T20:08:04+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_phase4_quiet_fix.md
   check_id: CHECK-QUIET-FIX-02
   attempt: 1
   spec_revision: 1
   command: "python Code/probes/probe_phase4_quiet_fix.py"
   ---

   # Run report

   ## Goal

   Test if the quiet early-break guard removes the `[1,319]` split at B=320.

   ## Commands

   ```text
   python Code/probes/probe_phase4_quiet_fix.py
   ```

   ## Observed output (trimmed)

   Full rows: `Code/probes/out/phase4_quiet_fix/fix.json`. Policy pass table: <PASS_TABLE>. Floor: <FLOOR>.

   ## Result

   <RESULT>

   ## Facts

   Pass table: <PASS_TABLE>. Floor: <FLOOR>.

   ## Guesses

   None.

   ## Assumptions checked

   Early-break guard: pass table. A-54: no OOM.

   ## Tried

   2 fresh servers, 24 callramp calls.

   ## Open question for planner

   Does a guarded quiet policy pass B=320 at p95 <= 350 ms?

   ## Attempt diff

   First attempt. Added `ARSENAL_CALL_FIRST_MIN_EARLY=32`.

   ## Smallest repro

   `python Code/probes/probe_phase4_quiet_fix.py`
   ```
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Fix the named run report field. Run `verify:` again.
result: StageSet validation passed.
### T005: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-phase4-quiet-fix.md
context: Record the code change and probe run.
do:
- [x] 1. CREATE `.stageset/sessions/coding-phase4-quiet-fix.md` with the block below.

   ```markdown
   ---
   type: CODING
   time: 2026-11-22T20:08:04+05:30
   summary: Guard quiet early break and test B=320 formation.
   paths: Code/batch/server.py; Code/probes/probe_phase4_quiet_fix.py; Code/probes/out/phase4_quiet_fix/fix.json; .stageset/runs/20261122-200804-RUN.md
   related: IDEA-0008; SSLD-029; FACT-0155; 20261122-200804-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Guard early break with `ARSENAL_CALL_FIRST_MIN_EARLY` default 32.

   ## Outcomes

   - Probe result is in `20261122-200804-RUN`.

   ## Follow-up

   - Planner reads the run report. If pass, wire policy. If fail, report floor.
   ```
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Fix the event. Run `verify:` again.
result: StageSet validation passed.
### T006: Update probe metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_phase4_quiet_fix.md
context: Mark probe DONE.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_phase4_quiet_fix.md`: replace `@stageset implemented_revision: 0` with `@stageset implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_phase4_quiet_fix.md`: replace `@stageset status: READY` with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_phase4_quiet_fix.md`: replace `@stageset implemented_in: -` with `@stageset implemented_in: .stageset/sessions/coding-phase4-quiet-fix.md`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_phase4_quiet_fix.md').read_text(); print(re.search(r'implemented_revision: (\d+)',s).group(1), re.search(r'status: (\w+)',s).group(1))"`
expect: 1 DONE
if_fail: Fix the three metadata lines. Run `verify:` again.
result: 1 DONE
### T007: Sync and validate
status: DONE
blocked_reason:
file: .stageset/DIGEST.md
context: Rebuild tracker and digest.
do:
- [x] 1. RUN `python scripts/stageset-status.py --sync`.
- [x] 2. RUN `python scripts/stageset-status.py --validate`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Fix the named file. Run `verify:` again.
result: StageSet validation passed.
