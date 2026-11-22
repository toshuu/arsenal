<!-- ss-living-doc v1 -->
# SSLD-026: Phase 4 formation policy probe

## STATE
doc_id: SSLD-026
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Probes/probe_phase4_formation.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-026-phase4-formation.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-026-phase4-formation.md --sync

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

- `20261122-192327-RUN` shows a 2-4 row early batch at `window=5` ms.
- The cap is not the cause. The dispatch policy is the cause.
- `_collect_call_first_quiet` already exists. Test it. Do not add new app code.
- Pick the policy that gives one batch at the largest B under 350 ms.

## TASKS

### T001: Create the formation probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_formation.py
context: This probe changes the window, quiet, and hard cap env between cells. It writes one JSON file with 72 rows.
do:
- [x] 1. CREATE `Code/probes/probe_phase4_formation.py` with the code block below.
- [x] 2. CHECK that the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/probe_phase4_formation.py`.

   ```python
   """Phase 4 formation probe: find a call_first policy that keeps one batch."""
   from __future__ import annotations
   import json, os, sys, time
   from pathlib import Path

   ROOT = Path(__file__).resolve().parents[2]
   os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
   os.environ.setdefault("ARSENAL_DEBUG", "1")
   os.environ.setdefault("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts")
   os.environ.setdefault("ARSENAL_MODEL_DIR", str(ROOT / "Code/model"))
   os.environ.setdefault("ARSENAL_VOICE", "/kaggle/working/refHD.wav")
   os.environ.setdefault("ARSENAL_PREWARM", "0")
   CAP = 640
   for key, value in {
       "ARSENAL_MAX_QUEUE": "4096",
       "ARSENAL_MAX_ROWS": str(CAP),
       "ARSENAL_MAX_BATCH": str(CAP),
       "ARSENAL_CALL_FIRST_MAX_BATCH": str(CAP),
       "ARSENAL_CALL_FIRST_SUB_BATCH": str(CAP),
   }.items():
       os.environ.setdefault(key, value)

   sys.path.insert(0, str(ROOT / "Code"))
   from fastapi.testclient import TestClient
   from batch.server import create_app

   TEXT = "Hello, can you hear me clearly right now?"
   OUT = ROOT / "Code/probes/out/phase4_formation"
   POLICIES = [
       {"name": "default", "window": 150, "quiet": 0, "hard": 0},
       {"name": "q2h20", "window": 150, "quiet": 2, "hard": 20},
       {"name": "q2h30", "window": 150, "quiet": 2, "hard": 30},
       {"name": "q3h40", "window": 150, "quiet": 3, "hard": 40},
   ]
   BS = [224, 320, 448]
   MODES = ["sentence", "utterance"]
   CALLS = 3


   def main():
       OUT.mkdir(parents=True, exist_ok=True)
       app = create_app()
       rows = []
       with TestClient(app) as client:
           for _ in range(300):
               if client.get("/health").json().get("ready"):
                   break
               time.sleep(1)
           else:
               raise SystemExit("server not ready")
           metrics = app.state.metrics
           worker = app.state.worker
           for policy in POLICIES:
               os.environ["ARSENAL_BATCH_WINDOW_MS"] = str(policy["window"])
               os.environ["ARSENAL_CALL_FIRST_QUIET_MS"] = str(policy["quiet"])
               os.environ["ARSENAL_CALL_FIRST_HARD_CAP_MS"] = str(policy["hard"])
               worker.reload_config()
               for mode in MODES:
                   for b in BS:
                       for call in range(CALLS):
                           before = len(metrics.batch_size)
                           url = (
                               "/debug/callramp?b=%d&repeats=1&first_only=1"
                               "&stream_mode=%s&first_max_frames=8&text=%s"
                               % (b, mode, TEXT.replace(" ", "%20"))
                           )
                           response = client.get(url)
                           response.raise_for_status()
                           run = response.json()["runs"][0]
                           first = run.get("first_byte_ms") or {}
                           row = {
                               "policy": policy["name"],
                               "window": policy["window"],
                               "quiet": policy["quiet"],
                               "hard": policy["hard"],
                               "mode": mode,
                               "b": b,
                               "call": call,
                               "warm": call > 0,
                               "p50": first.get("p50"),
                               "p95": first.get("p95"),
                               "errors": run.get("errors"),
                               "batch_sizes": run.get("batch_sizes"),
                           }
                           rows.append(row)
                           print(json.dumps(row), flush=True)
                           data = {"ok": True, "cap": CAP, "policies": POLICIES, "rows": rows}
                           (OUT / "formation.json").write_text(json.dumps(data, indent=2))
       data = {"ok": True, "cap": CAP, "policies": POLICIES, "rows": rows}
       (OUT / "formation.json").write_text(json.dumps(data, indent=2))
       print(json.dumps({"ok": True, "rows": len(rows)}))


   if __name__ == "__main__":
       main()
   ```
verify: `python -m py_compile Code/probes/probe_phase4_formation.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_phase4_formation.py`. Compare the file to the code block in step 1. Run `verify:` again.
result: exit:0

### T002: Run the formation probe
status: DONE
blocked_reason:
file: Code/probes/probe_phase4_formation.py
also_edit: Code/probes/out/phase4_formation/
context: Run 72 callramp calls. 4 policies, 2 modes, 3 B values, 3 calls per cell. The T4 must be free.
do:
- [x] 1. RUN `timeout 2400 python Code/probes/probe_phase4_formation.py`.
- [x] 2. CHECK that the command prints one final JSON line with `"rows": 72`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/phase4_formation/formation.json')); print(len(d['rows']), len(d['policies']))"`
expect: 72 4
if_fail: Run `nvidia-smi` and check free memory. Run the probe again. If it still fails, set status BLOCKED and write the failing output in blocked_reason.
result: 72 4

### T003: Create the run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-193729-RUN.md
context: The probe JSON exists. Write the PROBE run report with this exact id. Use values from the JSON. Do not invent values.
do:
- [x] 1. CREATE `.stageset/runs/20261122-193729-RUN.md` with the block below.
- [x] 2. EDIT the block: replace `<RESULT>`, `<WINNERS>`, and `<FLOOR>` with values from `Code/probes/out/phase4_formation/formation.json`.
- [x] 3. CHECK that no file in `.stageset/runs/` ends with `.reserve`.

   ```markdown
   ---
   id: 20261122-193729-RUN
   type: PROBE
   time: 2026-11-22T19:37:29+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_phase4_formation.md
   check_id: CHECK-PHASE4-FORM-02
   attempt: 1
   spec_revision: 1
   command: "python Code/probes/probe_phase4_formation.py"
   ---

   # Run report

   ## Goal

   Find a `call_first` formation policy that keeps B=320 and B=448 in one batch under 350 ms.

   ## Commands

   ```text
   python Code/probes/probe_phase4_formation.py
   ```

   ## Observed output (trimmed)

   Full rows are in `Code/probes/out/phase4_formation/formation.json`. Trimmed: only the winning pairs and the floor are shown here.

   Winners `(policy, B)` with one batch and p95 <= 350: <WINNERS>.

   Floor: <FLOOR>.

   ## Result

   <RESULT>

   ## Facts

   The winning pairs are <WINNERS>. The floor is <FLOOR>. All rows have `batch_sizes`.

   ## Guesses

   None.

   ## Assumptions checked

   A-49: `reload_config` applied each policy because the batch sizes changed between policies. A-50: not confirmed. The in-process p95 is an estimate.

   ## Tried

   One server start. 72 callramp calls.

   ## Open question for planner

   Confirm the winner on a real uvicorn server.

   ## Attempt diff

   First attempt.

   ## Smallest repro

   `python Code/probes/probe_phase4_formation.py`
   ```
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix only the named run report field. Run `verify:` again.
result: StageSet validation passed.

### T004: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-phase4-formation.md
context: The probe ran and the run report exists. Record one CODING event for this session.
do:
- [x] 1. CREATE `.stageset/sessions/coding-phase4-formation.md` with the block below.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the validation error. Fix the event `time` or `type` value. Run `verify:` again.
result: StageSet validation passed.

   ```markdown
   ---
   type: CODING
   time: 2026-11-22T19:37:29+05:30
   summary: Run the Phase 4 formation policy probe on the local T4.
   paths: Code/probes/probe_phase4_formation.py; Code/probes/out/phase4_formation/formation.json; .stageset/runs/20261122-193729-RUN.md; Skeletons/Probes/probe_phase4_formation.md
   related: IDEA-0008; SSLD-026; FACT-0152; 20261122-193729-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Test four `call_first` formation policies at cap 640.

   ## Outcomes

   - The probe ran. The measured values are in `20261122-193729-RUN`.

   ## Follow-up

   - The planner reads the run report and picks the policy.
   ```

### T005: Update the probe metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_phase4_formation.md
context: The probe ran and the evidence exists. Record that the probe implements revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_phase4_formation.md`: find line `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_phase4_formation.md`: find line `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_phase4_formation.md`: find line `@stageset implemented_in: -` and replace it with `@stageset implemented_in: .stageset/sessions/coding-phase4-formation.md`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_phase4_formation.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)',s).group(1), re.search(r'@stageset status: (\w+)',s).group(1))"`
expect: 1 DONE
if_fail: Open `Skeletons/Probes/probe_phase4_formation.md`. Fix the three metadata lines. Run `verify:` again.
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
