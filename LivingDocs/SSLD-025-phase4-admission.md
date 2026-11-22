<!-- ss-living-doc v1 -->
# SSLD-025: Phase 4 admission and cap probe

## STATE
doc_id: SSLD-025
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Probes/probe_phase4_admission.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-025-phase4-admission.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-025-phase4-admission.md --sync

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

- The Phase 2 B-ramp split B=320 and B=448 into two batches.
- The default `ARSENAL_MAX_BATCH` and `ARSENAL_MAX_ROWS` is 224.
- The older in-process sweep shows B=384 in one batch when the cap is 640.
- This probe repeats the test on the current code with the `sentence` and `utterance` modes.
- The result decides if Phase 4 is a cap change or a `BatchedStream` code change.

## TASKS

### T001: Create the admission probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_admission.py
context: This probe starts one local server with a cap of 640 and measures B=224, 320, 448 for both quality modes.
do:
- [x] 1. CREATE `Code/probes/probe_phase4_admission.py` with the code block below.
- [x] 2. CHECK that the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/probe_phase4_admission.py`.

   ```python
   """Phase 4 admission probe: cap 640, B=224/320/448, sentence and utterance."""
   from __future__ import annotations
   import argparse, json, os, subprocess, sys, time
   from pathlib import Path
   import requests

   ROOT = Path(__file__).resolve().parents[2]
   REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
   PORT = int(os.getenv("ARSENAL_PHASE4_PORT", "8123"))
   TEXT = "Hello, can you hear me clearly right now?"
   OUT = ROOT / "Code/probes/out/phase4_admission"


   def wait(base, timeout=300):
       end = time.time() + timeout
       while time.time() < end:
           try:
               r = requests.get(base + "/health", timeout=2)
               if r.ok and r.json().get("ready"):
                   return
           except Exception:
               pass
           time.sleep(1)
       raise RuntimeError("server not ready")


   def main():
       ap = argparse.ArgumentParser()
       ap.add_argument("--cap", type=int, default=640)
       ap.add_argument("--reps", type=int, default=4)
       ap.add_argument("--out", type=Path, default=OUT / "admission.json")
       args = ap.parse_args()
       args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
       args.out.parent.mkdir(parents=True, exist_ok=True)

       env = os.environ.copy()
       env.update({
           "ARSENAL_PREWARM": "0",
           "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
           "ARSENAL_VOICE": str(REF),
           "ARSENAL_DEBUG": "1",
           "ARSENAL_MAX_QUEUE": "4096",
           "ARSENAL_MAX_ROWS": str(args.cap),
           "ARSENAL_MAX_BATCH": str(args.cap),
           "ARSENAL_BATCH_TARGET": str(args.cap),
           "ARSENAL_CALL_FIRST_MAX_BATCH": str(args.cap),
       })
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
                   for rep in range(args.reps):
                       params = {
                           "b": b, "repeats": 1, "first_only": 1,
                           "stream_mode": mode, "first_max_frames": 8,
                           "window": 5, "text": TEXT,
                       }
                       r = requests.get(base + "/debug/callramp", params=params, timeout=600)
                       r.raise_for_status()
                       run = r.json()["runs"][0]
                       fb = run.get("first_byte_ms") or {}
                       row = {
                           "mode": mode, "b": b, "rep": rep, "warm": rep > 0,
                           "p50": fb.get("p50"), "p95": fb.get("p95"),
                           "errors": run.get("errors"),
                           "batch_sizes": run.get("batch_sizes"),
                           "vram_after": (run.get("vram_mb") or {}).get("after"),
                       }
                       rows.append(row)
                       print(json.dumps(row), flush=True)
                       args.out.write_text(json.dumps({"ok": True, "cap": args.cap, "rows": rows}, indent=2))
       finally:
           proc.terminate()
           try:
               proc.wait(timeout=20)
           except Exception:
               proc.kill()
           log.close()
       args.out.write_text(json.dumps({"ok": True, "cap": args.cap, "rows": rows}, indent=2))
       print(json.dumps({"ok": True, "out": str(args.out), "rows": len(rows)}))


   if __name__ == "__main__":
       main()
   ```
verify: `python -m py_compile Code/probes/probe_phase4_admission.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_phase4_admission.py`. Compare the file to the code block in step 1. Run `verify:` again.
result: exit code 0

### T002: Run the admission probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_admission.py
also_edit: Code/probes/out/phase4_admission/
context: Run 24 callramp calls with cap 640. B=224, 320, 448. 4 reps per cell. The T4 must be free.
do:
- [x] 1. RUN `timeout 2400 python Code/probes/probe_phase4_admission.py --cap 640 --reps 4`.
- [x] 2. CHECK that the command prints one final JSON line with `"rows": 24`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/phase4_admission/admission.json')); print(len(d['rows']), sorted({r['b'] for r in d['rows']}))"`
expect: 24 [224, 320, 448]
if_fail: Run `nvidia-smi` and check free memory. Run the probe again. If it still fails, set status BLOCKED and write the failing output in blocked_reason.
result: 24 [224, 320, 448]

### T003: Create the run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-192327-RUN.md
context: The probe JSON exists. Write the PROBE run report with this exact id. Use values from the JSON. Do not invent values.
do:
- [x] 1. CREATE `.stageset/runs/20261122-192327-RUN.md` with the block below.
- [x] 2. EDIT the block: replace `<RESULT>`, `<ERRORS>`, `<SINGLE_B320>`, `<BEST_P95_B320>`, and `<P95_SET>` with the values from `Code/probes/out/phase4_admission/admission.json`.
- [x] 3. DELETE `.stageset/runs/.20261122-192327-RUN.reserve`.

   ```markdown
   ---
   id: 20261122-192327-RUN
   type: PROBE
   time: 2026-11-22T19:23:27+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_phase4_admission.md
   check_id: CHECK-PHASE4-ADM-01
   attempt: 1
   spec_revision: 1
   command: "python Code/probes/probe_phase4_admission.py --cap 640 --reps 4"
   ---

   # Run report

   ## Goal

   Show if a cap of 640 keeps B=320 and B=448 in one batch for the sentence and utterance modes.

   ## Commands

   ```text
   python Code/probes/probe_phase4_admission.py --cap 640 --reps 4
   ```

   ## Observed output (trimmed)

   Read `Code/probes/out/phase4_admission/admission.json`. Put the 24 rows here. State `trimmed: full rows kept`.

   ## Result

   <RESULT>

   ## Facts

   Errors: <ERRORS>. Warm B=320 single batch: <SINGLE_B320>. Best warm B=320 p95: <BEST_P95_B320> ms. Warm B=320 p95 set: <P95_SET>.

   ## Guesses

   None.

   ## Assumptions checked

   A-47: check every row has `batch_sizes` and `p95`. A-48: `<ERRORS>` errors at B=448.

   ## Tried

   One server start. 24 callramp calls.

   ## Open question for planner

   None.

   ## Attempt diff

   First attempt.

   ## Smallest repro

   `python Code/probes/probe_phase4_admission.py --cap 640 --reps 4`
   ```
- [x] 4. CHECK that no file in `.stageset/runs/` ends with `.reserve`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix only the named run report field. Run `verify:` again.
result: StageSet validation passed.

### T004: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-phase4-admission.md
context: The probe ran and the run report exists. Record one CODING event for this session.
do:
- [x] 1. CREATE `.stageset/sessions/coding-phase4-admission.md` with the block below.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the event `time` or `type` value. Run `verify:` again.
result: StageSet validation passed.

   ```markdown
   ---
   type: CODING
   time: 2026-11-22T19:23:27+05:30
   summary: Run the Phase 4 admission probe with the cap raised to 640.
   paths: Code/probes/probe_phase4_admission.py; Code/probes/out/phase4_admission/admission.json; .stageset/runs/20261122-192327-RUN.md; Skeletons/Probes/probe_phase4_admission.md
   related: IDEA-0008; SSLD-025; 20261122-192327-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Test the cap before a `BatchedStream` change.

   ## Outcomes

   - The probe ran. The measured values are in `20261122-192327-RUN`.

   ## Follow-up

   - The planner reads the run report and updates the facts and IDEA-0008.
   ```

### T005: Update the probe metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_phase4_admission.md
context: The probe ran and the evidence exists. Record that the probe implements revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_phase4_admission.md`: find line `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_phase4_admission.md`: find line `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_phase4_admission.md`: find line `@stageset implemented_in: -` and replace it with `@stageset implemented_in: .stageset/sessions/coding-phase4-admission.md`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_phase4_admission.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)',s).group(1), re.search(r'@stageset status: (\w+)',s).group(1))"`
expect: 1 DONE
if_fail: Open `Skeletons/Probes/probe_phase4_admission.md`. Fix the three metadata lines. Run `verify:` again.
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
