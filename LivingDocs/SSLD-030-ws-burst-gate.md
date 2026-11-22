<!-- ss-living-doc v1 -->
# SSLD-030: Real WebSocket burst gate

## STATE
doc_id: SSLD-030
status: DONE
current_task: T007
tasks_done: 7
tasks_total: 7
skeleton: Skeletons/Probes/probe_ws_burst_gate.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-030-ws-burst-gate.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-030-ws-burst-gate.md --sync

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

Ultimate direction: pure raw frame streaming, maximum stable B, and the lowest
time to the first sound. The WebSocket is already connected. The clock starts
at text send and stops at the first audio byte.

Current facts:

- B=224 `sentence` is stable at 316 to 321 ms in the server fast path
  (FACT-0154).
- B=320 is one batch, but above 350 ms (FACT-0154).
- No client-side end-to-end gate exists at the default config.

This SSLD adds no app change. It measures the real WS path at B=224 and B=320
with `sentence`, the default quality mode. The result decides the next step:
lock B=224 or start continuous admission for more B.

## TASKS

### T001: Create the WS burst gate probe
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
context: This probe starts one fresh server and runs the existing burst client for B=224 and B=320. It writes one JSON summary.
do:
- [x] 1. CREATE `Code/probes/probe_ws_burst_gate.py` with the code block below.
- [x] 2. CHECK the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/probe_ws_burst_gate.py`.

   ```python
   """Real WebSocket burst gate at the default call config."""

   from __future__ import annotations

   import json
   import os
   import subprocess
   import sys
   import time
   from pathlib import Path

   import requests

   ROOT = Path(__file__).resolve().parents[2]
   OUT = ROOT / "Code/probes/out/ws_burst_gate"
   REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
   PORT = int(os.getenv("ARSENAL_WS_GATE_PORT", "8140"))
   TEXT = "Hello, can you hear me clearly right now?"
   BATCHES = [224, 320]


   def wait_ready(base: str, timeout_s: float = 300.0) -> None:
       end = time.time() + timeout_s
       while time.time() < end:
           try:
               response = requests.get(base + "/health", timeout=2)
               if response.ok and response.json().get("ready"):
                   return
           except Exception:
               pass
           time.sleep(1)
       raise RuntimeError("server not ready")


   def main() -> int:
       OUT.mkdir(parents=True, exist_ok=True)
       env = os.environ.copy()
       env.update({
           "ARSENAL_PREWARM": "0",
           "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
           "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
           "ARSENAL_VOICE": str(REF),
           "ARSENAL_DEBUG": "1",
           "ARSENAL_MAX_QUEUE": "4096",
           "ARSENAL_MAX_ROWS": "448",
           "ARSENAL_MAX_BATCH": "448",
           "ARSENAL_CALL_FIRST_MAX_BATCH": "448",
           "ARSENAL_CALL_FIRST_SUB_BATCH": "448",
           "ARSENAL_BATCH_WINDOW_MS": "150",
           "ARSENAL_CALL_STREAM_MODE": "sentence",
       })
       base = "http://127.0.0.1:%d" % PORT
       log = (OUT / "server.log").open("w", encoding="utf-8")
       proc = subprocess.Popen(
           [sys.executable, "-m", "uvicorn", "batch.server:app",
            "--host", "127.0.0.1", "--port", str(PORT)],
           cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT,
       )
       rows = []
       try:
           wait_ready(base)
           for batch in BATCHES:
               path = OUT / ("burst_%d.json" % batch)
               command = [
                   sys.executable, str(ROOT / "Code/probes/call_load_client.py"),
                   "--url", base, "--mode", "burst", "--b", str(batch),
                   "--repeats", "4", "--warmups", "2",
                   "--text", TEXT, "--out", str(path),
               ]
               subprocess.run(
                   command, cwd=str(ROOT), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
               )
               data = json.loads(path.read_text(encoding="utf-8"))
               runs = data.get("runs", [])
               rows.append({
                   "b": batch,
                   "p50_of_p50": data.get("p50_of_p50"),
                   "median_p95": data.get("median_p95"),
                   "p95_of_p95": data.get("p95_of_p95"),
                   "errors": data.get("errors"),
                   "connect_fail": data.get("connect_fail"),
                   "batch_sizes": [
                       (run.get("server") or {}).get("batch_size_after")
                       for run in runs
                   ],
                   "chunk_ms": [
                       (run.get("server") or {}).get("chunk_ms_after")
                       for run in runs
                   ],
                   "runs": runs,
               })
       finally:
           proc.terminate()
           try:
               proc.wait(timeout=20)
           except Exception:
               proc.kill()
           log.close()
       main_row = next((row for row in rows if row["b"] == 224), None)
       gate = bool(
           main_row
           and main_row["errors"] == 0
           and main_row["p95_of_p95"] is not None
           and main_row["p95_of_p95"] <= 350.0
       )
       out = {
           "ok": True,
           "gate_224": gate,
           "text": TEXT,
           "stream_mode": "sentence",
           "batches": BATCHES,
           "rows": rows,
       }
       (OUT / "gate.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
       summary = {
           "gate_224": gate,
           "p95": {row["b"]: row["p95_of_p95"] for row in rows},
           "errors": sum(int(row["errors"] or 0) for row in rows),
       }
       print(json.dumps(summary))
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```
verify: `python -m py_compile Code/probes/probe_ws_burst_gate.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_ws_burst_gate.py`. Compare it to the code block in step 1. Run `verify:` again.
result: exit code 0

### T002: Run the WS burst gate
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
also_edit: Code/probes/out/ws_burst_gate/
context: The T4 must be free. This runs B=224 and B=320 with 2 warmups and 5 measured burst repetitions. It writes gate.json. Probe fixed per owner: per-rep WS open/close, stagger 64, drain 10s, partial JSON, 20s per-stream timeout, ALL-warm-reps gate.
do:
- [x] 1. RUN `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader`.
- [x] 2. RUN `timeout 2400 python Code/probes/probe_ws_burst_gate.py`.
- [x] 3. CHECK that the final line is JSON with key `gate_224`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print(len(d['rows']), [r['b'] for r in d['rows']])"`
expect: 2 [224, 320]
if_fail: Run `nvidia-smi`. Stop other GPU work. Run the probe again. If it fails again, set status BLOCKED and write the error in blocked_reason.
result: 2 [224, 320]

### T003: Create the run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-210000-RUN.md
context: Write the PROBE report. Use the real values from gate.json. Do not invent values.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors'], 'batch': r['batch_sizes']} for r in d['rows']})"`.
- [x] 2. CREATE `.stageset/runs/20261122-210000-RUN.md` with the block below.
- [x] 3. EDIT `.stageset/runs/20261122-210000-RUN.md`: replace `<TABLE>` with the output of step 1.
- [x] 4. EDIT `.stageset/runs/20261122-210000-RUN.md`: replace `<RESULT>` with `PASS` if the 224 entry has `errors` 0 and `p95` <= 350. Else replace it with `FAIL`.
- [x] 5. CHECK that no file in `.stageset/runs/` ends with `.reserve`.

   ```markdown
   ---
   id: 20261122-210000-RUN
   type: PROBE
   time: 2026-11-22T21:00:00+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_ws_burst_gate.md
   check_id: CHECK-WS-GATE-02
   attempt: 1
   spec_revision: 1
   command: "python Code/probes/probe_ws_burst_gate.py"
   ---

   # Run report

   ## Goal

   Prove the first-sound gate on the real WebSocket path at the default call config. B=224 is the main gate. B=320 is the next-B data point.

   ## Commands

   ```text
   python Code/probes/probe_ws_burst_gate.py
   ```

   ## Observed output (trimmed)

   Full rows: `Code/probes/out/ws_burst_gate/gate.json`. Gate table: <TABLE>.

   ## Result

   <RESULT>

   ## Facts

   Gate table: <TABLE>. The client pre-connects and starts each WS before the barrier. The clock starts at text send and stops at the first audio byte.

   ## Guesses

   None.

   ## Assumptions checked

   - Default `ARSENAL_BATCH_TARGET=32` does not add the full 150 ms window wait at B=224.
   - `sentence` sends raw frames with no pause compression.

   ## Tried

   One fresh server. Two B values. 2 warmups and 4 measured burst repetitions per B.

   ## Open question for planner

   Is B=224 `sentence` a stable end-to-end operating point? Does B=320 stay above 350 ms?

   ## Attempt diff

   First attempt. No app code change.

   ## Smallest repro

   `python Code/probes/probe_ws_burst_gate.py`
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/runs/20261122-210000-RUN.md').read_text(); print('<RESULT>' not in s, '## Result' in s, '## Facts' in s)"`
expect: True True True
if_fail: Open the run report. Replace `<RESULT>` and `<TABLE>`. Add the missing section. Run `verify:` again.
result: True True True

### T004: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-ssld-030-ws-burst-gate.md
context: Record one CODING event for this probe session. Use the real current time.
do:
- [x] 1. RUN `date +%Y-%m-%dT%H:%M:%S%:z`.
- [x] 2. CREATE `.stageset/sessions/coding-ssld-030-ws-burst-gate.md` with the block below.
- [x] 3. EDIT `.stageset/sessions/coding-ssld-030-ws-burst-gate.md`: replace `<TIME>` with the output of step 1.

   ```markdown
   ---
   type: CODING
   time: <TIME>
   summary: Run the real WebSocket burst gate at the default call config.
   paths: Code/probes/probe_ws_burst_gate.py; Code/probes/out/ws_burst_gate/gate.json; .stageset/runs/20261122-210000-RUN.md; Skeletons/Probes/probe_ws_burst_gate.md
   related: IDEA-0008; SSLD-030; FACT-0154; 20261122-210000-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Measure the real WS path with `sentence` at B=224 and B=320.
   - Do not change app code in this step.

   ## Outcomes

   - Gate table and decision are in `20261122-210000-RUN`.

   ## Follow-up

   - Planner reads the run report. If B=224 passes, lock it. If not, inspect the client and server phase gaps.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/sessions/coding-ssld-030-ws-burst-gate.md').read_text(); print('<TIME>' not in s, 'type: CODING' in s)"`
expect: True True
if_fail: Open the event. Replace `<TIME>` with the real time. Run `verify:` again.
result: True True

### T005: Update the probe skeleton metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_ws_burst_gate.md
context: The probe ran and the evidence exists. Record that the probe implements revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset implemented_in: -` and replace it with `@stageset implemented_in: .stageset/sessions/coding-ssld-030-ws-burst-gate.md`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_ws_burst_gate.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)', s).group(1), re.search(r'@stageset status: (\w+)', s).group(1))"`
expect: 1 DONE
if_fail: Open `Skeletons/Probes/probe_ws_burst_gate.md`. Fix the three metadata lines. Run `verify:` again.
result: 1 DONE

### T006: Add the gate decision to IDEA-0008
status: DONE
blocked_reason:
file: Ideas/IDEA-0008-natural-live-call-streaming.md
context: Record the newest gate result in the idea. Use the real values from the run report.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print(json.dumps({r['b']:{'p50':r['p50_of_p50'],'p95':r['p95_of_p95'],'errors':r['errors']} for r in d['rows']}))"`.
- [x] 2. APPEND to `Ideas/IDEA-0008-natural-live-call-streaming.md` the block below.
- [x] 3. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<TABLE>` with the output of step 1.

   ```markdown

   ## Phase 5 WS gate

   `20261122-210000-RUN` measured the real WS path with `sentence` at the default config.
   Table: <TABLE>.

   Decision: if B=224 `errors` is 0 and `p95` <= 350 ms, B=224 `sentence` is the
   locked operating point. If not, inspect the client send and server phase gaps.

   B=320 stays a measurement point. Do not set it as a target without a new
   formation or admission change.
   ```
verify: `grep -c "## Phase 5 WS gate" Ideas/IDEA-0008-natural-live-call-streaming.md`
expect: 1
if_fail: Open the idea file. Check the appended heading. Run `verify:` again.
result: 1

### T007: Sync and validate
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
