<!-- ss-living-doc v1 -->
# SSLD-033: WS low-latency gate with confirmed formation
## STATE
doc_id: SSLD-033
status: DONE
current_task: T008
tasks_done: 8
tasks_total: 8
skeleton: Skeletons/Probes/probe_ws_burst_gate.md
spec_revision: 5
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-033-formation-modes.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-033-formation-modes.md --sync
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
Spec 4 was BLOCKED. Two errors in the probe spec, not in the app:
- `quiet=5` and `MIN_EARLY=32` split the burst into about 32-row batches.
  The p95 rose to 1878 ms.
- `utterance` forces 512 frames per row. At B=224 this OOMs on T4.
This revision uses the formation that passed in FACT-0139: cap 640, target 640,
MAX_FRAMES 192, CALL_FIRST_MAX_FRAMES 8, quiet 50, hard cap 300, grace 20,
prewarm on, and no MIN_EARLY override. It tests only `sentence`, at B=224,
320, and 384.
Both modes stay in the app. The low-latency config is the default for voice
calls. Mode is selectable per request from the WS `start` payload and the text
payload. This document does not change app code.
## STANDING
Final standing after this document: use `sentence` mode with the current
about-40-frame first chunk for WS. All three modes stay in the app and are
selectable from the API payload. No app code change.
Latest numbers are in `.stageset/runs/20261122-232457-RUN.md`,
`FACT-0159`, `FACT-0160`, and `RES-005`. Earlier SSLD-030 to SSLD-032 results
are superseded by this standing.
## TASKS
### T001: Pass max_frames from the gate client
status: DONE
blocked_reason:
file: Code/probes/ws_burst_gate_client.py
context: The confirmed run sends max_frames=8 in the text message. Do not change the timing code.
do:
- [x] 1. EDIT `Code/probes/ws_burst_gate_client.py`: find `async def one_call(connection: dict, text: str, timeout_s: float) -> dict:` and replace it with `async def one_call(connection: dict, text: str, timeout_s: float, max_frames: int) -> dict:`.
- [x] 2. EDIT `Code/probes/ws_burst_gate_client.py`: find the two lines `            "text": text,` and `            "first_only": True,` and replace them with the three lines `            "text": text,`, `            "max_frames": max_frames,`, `            "first_only": True,`.
- [x] 3. EDIT `Code/probes/ws_burst_gate_client.py`: find `async def burst(live: list[dict], text: str, timeout_s: float) -> dict:` and replace it with `async def burst(live: list[dict], text: str, timeout_s: float, max_frames: int) -> dict:`.
- [x] 4. EDIT `Code/probes/ws_burst_gate_client.py`: find `        return await one_call(connection, text, timeout_s)` and replace it with `        return await one_call(connection, text, timeout_s, max_frames)`.
- [x] 5. EDIT `Code/probes/ws_burst_gate_client.py`: find `            result = await burst(live, args.text, args.timeout)` and replace it with `            result = await burst(live, args.text, args.timeout, args.max_frames)`.
- [x] 6. EDIT `Code/probes/ws_burst_gate_client.py`: find `    parser.add_argument("--mode", default="sentence")` and replace it with `    parser.add_argument("--mode", default="sentence")` then a new line `    parser.add_argument("--max-frames", type=int, default=8)`.
- [x] 7. RUN `python -m py_compile Code/probes/ws_burst_gate_client.py`.
verify: `python -c "import pathlib; s=pathlib.Path('Code/probes/ws_burst_gate_client.py').read_text(); print('max_frames' in s, '--max-frames' in s, 'args.max_frames' in s)"`
expect: True True True
if_fail: Compare the six find strings with the file. Do not edit other lines. Run step 7 again. If it fails twice, set status BLOCKED.
result: True True True
### T002: Rewrite the probe with the confirmed formation
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
context: One fresh server. Cap 640, target 640, mf8, quiet 50, hard 300, grace 20. Sentence only. B=224, 320, 384.
do:
- [x] 1. CREATE `Code/probes/probe_ws_burst_gate.py` with the code block below.
- [x] 2. RUN `python -m py_compile Code/probes/probe_ws_burst_gate.py`.
- [x] 3. CHECK that the file has `def main()`.
   ```python
   """Real WebSocket low-latency gate: confirmed quiet formation, max B."""
   from __future__ import annotations
   import hashlib
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
   BATCHES = [224, 320, 384]
   MODE = "sentence"
   CAP = 640
   FIRST_FRAMES = 8
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
           "ARSENAL_PREWARM": "1",
           "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
           "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
           "ARSENAL_VOICE": str(REF),
           "ARSENAL_DEBUG": "1",
           "ARSENAL_MAX_QUEUE": "4096",
           "ARSENAL_MAX_ROWS": str(CAP),
           "ARSENAL_MAX_BATCH": str(CAP),
           "ARSENAL_BATCH_TARGET": str(CAP),
           "ARSENAL_MAX_FRAMES": "192",
           "ARSENAL_BATCH_WINDOW_MS": "150",
           "ARSENAL_CALL_STREAM_MODE": MODE,
           "ARSENAL_CALL_FIRST_MAX_BATCH": str(CAP),
           "ARSENAL_CALL_FIRST_SUB_BATCH": str(CAP),
           "ARSENAL_CALL_FIRST_MAX_FRAMES": str(FIRST_FRAMES),
           "ARSENAL_CALL_CONT_MAX_FRAMES": "192",
           "ARSENAL_CALL_FIRST_QUIET_MS": "50",
           "ARSENAL_CALL_FIRST_HARD_CAP_MS": "300",
           "ARSENAL_CALL_FIRST_GRACE_MS": "20",
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
               requests.get(base + "/debug/reset", timeout=10)
               command = [
                   sys.executable, str(ROOT / "Code/probes/ws_burst_gate_client.py"),
                   "--url", base, "--b", str(batch),
                   "--repeats", "4", "--warmups", "2",
                   "--mode", MODE, "--max-frames", str(FIRST_FRAMES),
                   "--text", TEXT, "--out", str(path),
               ]
               subprocess.run(
                   command, cwd=str(ROOT), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
               )
               data = json.loads(path.read_text(encoding="utf-8"))
               server = requests.get(base + "/metrics", timeout=10).json()
               metrics = server.get("metrics", {})
               rows.append({
                   "mode": MODE,
                   "b": batch,
                   "p50_of_p50": data.get("p50_of_p50"),
                   "median_p95": data.get("median_p95"),
                   "p95_of_p95": data.get("p95_of_p95"),
                   "errors": data.get("errors"),
                   "connect_fail": data.get("connect_fail"),
                   "call_first_ms": metrics.get("call_first_ms"),
                   "call_first_wait_ms": metrics.get("call_first_wait_ms"),
                   "batch_wait_ms": metrics.get("batch_wait_ms"),
                   "batch_size": metrics.get("batch_size"),
                   "runs": data.get("runs", []),
               })
               time.sleep(1.0)
       finally:
           proc.terminate()
           try:
               proc.wait(timeout=20)
           except Exception:
               proc.kill()
           log.close()
       def passes(row: dict) -> bool:
           return bool(
               row["errors"] == 0
               and row["p95_of_p95"] is not None
               and row["p95_of_p95"] <= 350.0
           )
       passing = [row["b"] for row in rows if passes(row)]
       max_b = max(passing) if passing else None
       gate_224 = passes(next(row for row in rows if row["b"] == 224))
       gate_320 = passes(next(row for row in rows if row["b"] == 320))
       out = {
           "ok": True,
           "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "client_sha256": hashlib.sha256((ROOT / "Code/probes/ws_burst_gate_client.py").read_bytes()).hexdigest(),
           "gate_224": gate_224,
           "gate_320": gate_320,
           "max_b_under_350": max_b,
           "mode": MODE,
           "cap": CAP,
           "first_frames": FIRST_FRAMES,
           "text": TEXT,
           "batches": BATCHES,
           "rows": rows,
       }
       (OUT / "gate.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
       summary = {
           "gate_320": gate_320,
           "max_b_under_350": max_b,
           "p95": {str(row["b"]): row["p95_of_p95"] for row in rows},
           "errors": sum(int(row["errors"] or 0) for row in rows),
       }
       print(json.dumps(summary))
       return 0
   if __name__ == "__main__":
       raise SystemExit(main())
   ```
verify: `python -c "import ast,pathlib; s=pathlib.Path('Code/probes/probe_ws_burst_gate.py').read_text(); ast.parse(s); print('HARD_CAP' in s, '\"sentence\"' in s, 'gate_320' in s)"`
expect: True True True
if_fail: Compare the code block with the file. Run step 2 again. If it fails twice, set status BLOCKED.
result: True True True
### T003: Run the low-latency gate
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
also_edit: Code/probes/out/ws_burst_gate/
context: The T4 must be free. Delete the old result files. The probe starts one fresh server and writes new files.
do:
- [x] 1. RUN `rm -f Code/probes/out/ws_burst_gate/gate.json Code/probes/out/ws_burst_gate/burst_*.json`.
- [x] 2. RUN `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader`.
- [x] 3. RUN `timeout 1800 python Code/probes/probe_ws_burst_gate.py`.
- [x] 4. CHECK that the final line is JSON with `gate_320` and `max_b_under_350`.
verify: `python -c "import json,hashlib,pathlib; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); p=pathlib.Path('Code/probes/probe_ws_burst_gate.py'); c=pathlib.Path('Code/probes/ws_burst_gate_client.py'); print(len(d['rows']), d['probe_sha256']==hashlib.sha256(p.read_bytes()).hexdigest(), d['client_sha256']==hashlib.sha256(c.read_bytes()).hexdigest(), 'gate_320' in d, all(r['errors']==0 for r in d['rows']))"`
expect: 3 True True True True
if_fail: Run `nvidia-smi`. Stop other GPU work. Check server.log for OOM. Run steps 1 and 3 again. If it fails again, set status BLOCKED.
result: 3 True True True True
### T004: Create the low-latency run report
status: DONE
blocked_reason:
file: .stageset/runs/20261123-000000-RUN.md
context: Attempt 2 of the WS gate. Use only values from gate.json. Do not invent values.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors'], 'wait': (r.get('call_first_wait_ms') or {}).get('p50')} for r in d['rows']})"`.
- [x] 2. CREATE `.stageset/runs/20261123-000000-RUN.md` with the block below.
- [x] 3. EDIT `.stageset/runs/20261123-000000-RUN.md`: replace `<TABLE>` with the output of step 1.
- [x] 4. EDIT `.stageset/runs/20261123-000000-RUN.md`: replace `<GATE>` with `d['gate_320']` from gate.json.
- [x] 5. EDIT `.stageset/runs/20261123-000000-RUN.md`: replace `<MAXB>` with `d['max_b_under_350']` from gate.json.
- [x] 6. EDIT `.stageset/runs/20261123-000000-RUN.md`: replace `<WAIT>` with the B=320 `call_first_wait_ms.p50` from gate.json.
- [x] 7. EDIT `.stageset/runs/20261123-000000-RUN.md`: replace `<RESULT>` with `PASS` if `d['gate_320']` is true, else `FAIL`.
   ```markdown
   ---
   id: 20261123-000000-RUN
   type: PROBE
   time: 2026-11-23T00:00:00+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_ws_burst_gate.md
   check_id: CHECK-WS-GATE-02
   attempt: 2
   spec_revision: 5
   command: "python Code/probes/probe_ws_burst_gate.py"
   ---
   # Run report
   ## Goal
   Confirm the low-latency WS first-sound gate on the current app revision with
   the formation settings from FACT-0139.
   ## Commands
   ~~~text
   python Code/probes/probe_ws_burst_gate.py
   ~~~
   ## Observed output (trimmed)
   Full rows: `Code/probes/out/ws_burst_gate/gate.json`. Table: <TABLE>.
   Gate B=320: <GATE>. Max B under 350 ms: <MAXB>. B=320 formation wait p50: <WAIT> ms.
   Both SHA-256 values match the files on disk. The server was fresh. The mode was `sentence` with `max_frames=8`.
   ## Result
   <RESULT>
   ## Facts
   Table: <TABLE>. The clock starts at text send and stops at the first audio byte. Batch sizes p50 equal the call count. Formation wait p50 is 28.57 to 40.57 ms.
   ## Guesses
   None.
   ## Assumptions checked
   - The call-first batch closes when all active calls are present.
   - `sentence` mode with `max_frames=8` sends raw frames.
   ## Tried
   One fresh server. Three B values. 2 warmups and 4 measured burst repetitions per B.
   ## Open question for planner
   Is B=320 stable under the low-latency config? Should this config become the default for voice calls?
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/runs/20261123-000000-RUN.md').read_text(); print('<TABLE>' not in s, '<GATE>' not in s, '<MAXB>' not in s, '<WAIT>' not in s, '<RESULT>' not in s)"`
expect: True True True True True
if_fail: Use `Code/probes/out/ws_burst_gate/gate.json`. Do not invent values. If a placeholder is unclear, set status BLOCKED.
result: True True True True True
### T005: Update the idea with the low-latency result
status: DONE
blocked_reason:
file: Ideas/IDEA-0008-natural-live-call-streaming.md
context: Append a new section. Do not change old sections.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors']} for r in d['rows']})"`.
- [x] 2. APPEND to `Ideas/IDEA-0008-natural-live-call-streaming.md` the block below.
- [x] 3. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<TABLE>` with the output of step 1.
- [x] 4. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<GATE>` with the gate_320 bool from gate.json.
- [x] 5. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<MAXB>` with `max_b_under_350` from gate.json.
- [x] 6. APPEND one decision line: if `gate_320` is true, append `Use the low-latency sentence config with mf8 and quiet formation as the default for voice calls. Keep the mode selectable per request.`. Else append `The low-latency config still fails. Inspect formation and frame count.`
   ```markdown
   ## Phase 5 WS low-latency gate
   `20261123-000000-RUN` ran the real WS path with cap 640, target 640,
   `max_frames=8`, quiet 50, hard cap 300, and grace 20. It tests `sentence`
   only. `utterance` is not used because it OOMs at B=224 on T4.
   Table: <TABLE>
   Decision: B=320 gate `<GATE>`, max B under 350 ms `<MAXB>`.
   Both modes stay in the app. Mode and frame cap are per-request payload
   fields. This gate does not change app code.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('Ideas/IDEA-0008-natural-live-call-streaming.md').read_text(); print('## Phase 5 WS low-latency gate' in s, '<TABLE>' not in s, '<GATE>' not in s, '<MAXB>' not in s)"`
expect: True True True True
if_fail: Compare the placeholders. Use gate.json. If it fails twice, set status BLOCKED.
result: True True True True
### T006: Record the low-latency fact
status: DONE
blocked_reason:
file: .stageset/facts.md
context: Add one fact. Use only values from gate.json. The previous FACT-0158 row was not written.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print('; '.join('B%d p50 %.2f p95 %.2f wait %.2f errors %d' % (r['b'], r['p50_of_p50'], r['p95_of_p95'], (r.get('call_first_wait_ms') or {}).get('p50') or -1, r['errors']) for r in d['rows']))"`.
- [x] 2. APPEND to `.stageset/facts.md` the row below.
- [x] 3. EDIT `.stageset/facts.md`: replace `<TABLE>` with the output of step 1.
- [x] 4. EDIT `.stageset/facts.md`: replace `<GATE>` with `d['gate_320']` from gate.json.
- [x] 5. EDIT `.stageset/facts.md`: replace `<MAXB>` with `d['max_b_under_350']` from gate.json.
   ```markdown
   | FACT-0158 | 2026-11-23 | WS low-latency gate on current app, sentence mode, cap 640, target 640, max_frames=8, quiet 50, hard cap 300, grace 20. <TABLE>. B=320 gate <GATE>. Max B under 350 ms <MAXB>. | Project | CURRENT | `.stageset/runs/20261123-000000-RUN.md` |
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/facts.md').read_text(); print('FACT-0158' in s, '<TABLE>' not in s, '<GATE>' not in s, '<MAXB>' not in s)"`
expect: True True True True
if_fail: Use gate.json. If it fails twice, set status BLOCKED.
result: True True True True
### T007: Create the coding event and close the skeleton
status: DONE
blocked_reason:
file: .stageset/sessions/coding-ssld-033-formation.md
also_edit: Skeletons/Probes/probe_ws_burst_gate.md
context: Record the code change. Then close the probe skeleton at spec 5.
do:
- [x] 1. RUN `date +%Y-%m-%dT%H:%M:%S%:z`.
- [x] 2. CREATE `.stageset/sessions/coding-ssld-033-formation.md` with the block below.
- [x] 3. EDIT `.stageset/sessions/coding-ssld-033-formation.md`: replace `<TIME>` with the output of step 1.
- [x] 4. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: replace `@stageset status: READY` with `@stageset status: DONE`.
- [x] 5. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: replace `@stageset implemented_revision: 3` with `@stageset implemented_revision: 5`.
- [x] 6. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: replace `@stageset implemented_in: .stageset/sessions/coding-ssld-032-gate-client.md` with `@stageset implemented_in: .stageset/sessions/coding-ssld-033-formation.md`.
- [x] 7. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: replace `@stageset resolution_of: 20261122-230000-RUN` with `@stageset resolution_of: 20261123-000000-RUN`.
- [x] 8. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: replace `@stageset last_updated_in: .stageset/sessions/maintenance-ssld-033-spec5.md` with `@stageset last_updated_in: .stageset/sessions/coding-ssld-033-formation.md`.
   ```markdown
   ---
   type: CODING
   time: <TIME>
   summary: Add max_frames to the gate client and restore confirmed formation in the probe.
   paths: Code/probes/ws_burst_gate_client.py; Code/probes/probe_ws_burst_gate.py
   related: IDEA-0008; SSLD-033; 20261123-000000-RUN
   commit: -
   remote: -
   branch: -
   ---
   # Session notes
   ## Change
   - The client sends `max_frames` in the text message.
   - The probe uses cap 640, target 640, mf8, quiet 50, hard cap 300, grace 20.
   - The probe tests `sentence` at B=224, 320, and 384.
   ## Result
   See `.stageset/runs/20261123-000000-RUN.md`.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('Skeletons/Probes/probe_ws_burst_gate.md').read_text(); print('@stageset status: DONE' in s, '@stageset implemented_revision: 5' in s, 'coding-ssld-033-formation.md' in s, '20261123-000000-RUN' in s)"`
expect: True True True True
if_fail: Compare the metadata lines. If it fails twice, set status BLOCKED.
result: True True True True
### T008: Sync and validate
status: DONE
blocked_reason:
file: .stageset/DIGEST.md
context: Run the repo checks. Do not skip.
do:
- [x] 1. RUN `python scripts/stageset-status.py --sync`.
- [x] 2. RUN `python scripts/stageset-status.py --validate`.
verify: `python scripts/stageset-status.py --validate`
expect: StageSet validation passed.
if_fail: Read the error. Fix only the named file. Run both steps again. If it fails twice, set status BLOCKED.
result: StageSet validation passed.
