<!-- ss-living-doc v1 -->
# SSLD-027: Phase 4 real-server confirmation

## STATE
doc_id: SSLD-027
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Probes/probe_phase4_confirm.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-027-phase4-confirm.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-027-phase4-confirm.md --sync

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

- FACT-0153 says the default window gives one batch at all B in-process, but the
  p95 is over 350 ms at B=320.
- The in-process p95 is not a gate.
- Confirm on a separate-process server with the default window and no quiet.
- This probe does not change app code.

## TASKS

### T001: Create the confirmation probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_confirm.py
context: This probe starts one uvicorn server with the default window and cap 640. It writes 36 rows.
do:
- [x] 1. CREATE `Code/probes/probe_phase4_confirm.py` with the code block below.
- [x] 2. CHECK that the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/probe_phase4_confirm.py`.

   ```python
   """Phase 4 confirmation probe: default window, cap 640, real uvicorn server."""
   from __future__ import annotations
   import argparse, json, os, subprocess, sys, time
   from pathlib import Path
   import requests

   ROOT = Path(__file__).resolve().parents[2]
   REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
   PORT = int(os.getenv("ARSENAL_PHASE4_CONFIRM_PORT", "8125"))
   TEXT = "Hello, can you hear me clearly right now?"
   OUT = ROOT / "Code/probes/out/phase4_confirm"


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


   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--cap", type=int, default=640)
       parser.add_argument("--calls", type=int, default=6)
       parser.add_argument("--out", type=Path, default=OUT / "confirm.json")
       args = parser.parse_args()
       args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
       args.out.parent.mkdir(parents=True, exist_ok=True)

       env = os.environ.copy()
       env.update({
           "ARSENAL_PREWARM": "0",
           "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
           "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
           "ARSENAL_VOICE": str(REF),
           "ARSENAL_DEBUG": "1",
           "ARSENAL_MAX_QUEUE": "4096",
           "ARSENAL_MAX_ROWS": str(args.cap),
           "ARSENAL_MAX_BATCH": str(args.cap),
           "ARSENAL_CALL_FIRST_MAX_BATCH": str(args.cap),
           "ARSENAL_CALL_FIRST_SUB_BATCH": str(args.cap),
           "ARSENAL_CALL_FIRST_QUIET_MS": "0",
           "ARSENAL_CALL_FIRST_HARD_CAP_MS": "0",
       })
       env.pop("ARSENAL_BATCH_WINDOW_MS", None)
       log = (args.out.parent / "server.log").open("w")
       proc = subprocess.Popen(
           [sys.executable, "-m", "uvicorn", "batch.server:app",
            "--host", "127.0.0.1", "--port", str(PORT)],
           cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT,
       )
       rows = []
       try:
           base = "http://127.0.0.1:%d" % PORT
           wait(base)
           for mode in ["sentence", "utterance"]:
               for b in [224, 320, 448]:
                   for call in range(args.calls):
                       params = {
                           "b": b, "repeats": 1, "first_only": 1,
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
                           "mode": mode, "b": b, "call": call, "warm": call > 1,
                           "p50": first.get("p50"), "p95": first.get("p95"),
                           "errors": run.get("errors"),
                           "batch_sizes": run.get("batch_sizes"),
                           "vram_after": (run.get("vram_mb") or {}).get("after"),
                       }
                       rows.append(row)
                       print(json.dumps(row), flush=True)
                       data = {"ok": True, "cap": args.cap, "rows": rows}
                       args.out.write_text(json.dumps(data, indent=2))
       finally:
           proc.terminate()
           try:
               proc.wait(timeout=20)
           except Exception:
               proc.kill()
           log.close()
       data = {"ok": True, "cap": args.cap, "rows": rows}
       args.out.write_text(json.dumps(data, indent=2))
       print(json.dumps({"ok": True, "out": str(args.out), "rows": len(rows)}))


   if __name__ == "__main__":
       main()
   ```
verify: `python -m py_compile Code/probes/probe_phase4_confirm.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_phase4_confirm.py`. Compare the file to the code block in step 1. Run `verify:` again.
result: exit:0

### T002: Run the confirmation probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_confirm.py
also_edit: Code/probes/out/phase4_confirm/
context: Run 36 callramp calls. Default window. Cap 640. B=224, 320, 448. 6 calls per cell. The T4 must be free.
do:
- [x] 1. RUN `timeout 2400 python Code/probes/probe_phase4_confirm.py`.
- [x] 2. CHECK that the command prints one final JSON line with `"rows": 36`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/phase4_confirm/confirm.json')); print(len(d['rows']), sorted({r['b'] for r in d['rows']}))"`
expect: 36 [224, 320, 448]
if_fail: Run `nvidia-smi` and check free memory. Run the probe again. If it still fails, set status BLOCKED and write the failing output in blocked_reason.
result: 36 [224, 320, 448]

### T003: Create the run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-195007-RUN.md
context: The probe JSON exists. Write the PROBE run report with this exact id. Use values from the JSON. Do not invent values.
do:
- [x] 1. CREATE `.stageset/runs/20261122-195007-RUN.md` with the block below.
- [x] 2. EDIT the block: replace `<RESULT>`, `<B320_ONE_BATCH>`, `<B320_P95>`, and `<FLOOR>` with values from `Code/probes/out/phase4_confirm/confirm.json`.
- [x] 3. CHECK that no file in `.stageset/runs/` ends with `.reserve`.

   ```markdown
   ---
   id: 20261122-195007-RUN
   type: PROBE
   time: 2026-11-22T19:50:07+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_phase4_confirm.md
   check_id: CHECK-PHASE4-CONFIRM-02
   attempt: 1
   spec_revision: 1
   command: "python Code/probes/probe_phase4_confirm.py"
   ---

   # Run report

   ## Goal

   Confirm on a separate-process server that B=320 forms one batch with the default window and cap 640.

   ## Commands

   ```text
   python Code/probes/probe_phase4_confirm.py
   ```

   ## Observed output (trimmed)

   Full rows are in `Code/probes/out/phase4_confirm/confirm.json`. Trimmed: only the B=320 warm rows are shown here.

   B=320 all warm rows one batch: <B320_ONE_BATCH>.

   B=320 worst warm p95 by mode: <B320_P95>.

   Floor: <FLOOR>.

   ## Result

   <RESULT>

   ## Facts

   B=320 all warm rows one batch: <B320_ONE_BATCH>. B=320 worst warm p95 by mode: <B320_P95>. Floor: <FLOOR>. All rows have `batch_sizes`.

   ## Guesses

   None.

   ## Assumptions checked

   A-51: the result above. A-52: `<FLOOR>` has no OOM and no error.

   ## Tried

   One server start. 36 callramp calls.

   ## Open question for planner

   Is the B=320 p95 under the 350 ms gate, or is it the model floor?

   ## Attempt diff

   First attempt. This probe uses the default window. The earlier probes used a forced window.

   ## Smallest repro

   `python Code/probes/probe_phase4_confirm.py`
   ```
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix only the named run report field. Run `verify:` again.
result: StageSet validation passed.

### T004: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-phase4-confirm.md
context: The probe ran and the run report exists. Record one CODING event for this session.
do:
- [x] 1. CREATE `.stageset/sessions/coding-phase4-confirm.md` with the block below.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the event `time` or `type` value. Run `verify:` again.
result: StageSet validation passed.

   ```markdown
   ---
   type: CODING
   time: 2026-11-22T19:50:07+05:30
   summary: Confirm Phase 4 formation on a separate-process uvicorn server.
   paths: Code/probes/probe_phase4_confirm.py; Code/probes/out/phase4_confirm/confirm.json; .stageset/runs/20261122-195007-RUN.md; Skeletons/Probes/probe_phase4_confirm.md
   related: IDEA-0008; SSLD-027; FACT-0153; 20261122-195007-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Use the default window and cap 640.

   ## Outcomes

   - The probe ran. The measured values are in `20261122-195007-RUN`.

   ## Follow-up

   - The planner reads the run report and decides the Phase 4 action.
   ```

### T005: Update the probe metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_phase4_confirm.md
context: The probe ran and the evidence exists. Record that the probe implements revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_phase4_confirm.md`: find line `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_phase4_confirm.md`: find line `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_phase4_confirm.md`: find line `@stageset implemented_in: -` and replace it with `@stageset implemented_in: .stageset/sessions/coding-phase4-confirm.md`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_phase4_confirm.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)',s).group(1), re.search(r'@stageset status: (\w+)',s).group(1))"`
expect: 1 DONE
if_fail: Open `Skeletons/Probes/probe_phase4_confirm.md`. Fix the three metadata lines. Run `verify:` again.
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
