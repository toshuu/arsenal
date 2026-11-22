<!-- ss-living-doc v1 -->
# SSLD-032: Dedicated gate client and corrected WS gate

## STATE
doc_id: SSLD-032
status: DONE
current_task: T009
tasks_done: 9
tasks_total: 9
skeleton: Skeletons/Probes/probe_ws_burst_gate.md
spec_revision: 3
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-032-gate-client.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-032-gate-client.md --sync

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

This document replaces SSLD-031 from T004 onward. Do not run SSLD-031 again.

Reason for the change:

- The HEAD client calls `drain()` before each repetition.
- `drain()` waits for `active_call_sessions == 0`.
- The B clients stay connected, so this wait hits the 120 s timeout each time.
- The HEAD client sends `cancel` after each run. The server keeps `cancelled`
  true until the next `start`. A reused WebSocket then sends no audio.

Use one dedicated client. It opens the B sockets once. It does not send
`cancel` between runs. It does not call `drain()`. It keeps warmups out of the
p50 and p95. It writes SHA-256 bound output.

Do not change app code. Do not tune the collector.

## TASKS

### T001: Create the dedicated gate client
status: DONE
blocked_reason:
file: Code/probes/ws_burst_gate_client.py
context: One pre-connected socket set. 2 warmups and 4 measured runs. No cancel between runs. No drain. Warm-only stats.
do:
- [x] 1. CREATE `Code/probes/ws_burst_gate_client.py` with the code block below.
- [x] 2. CHECK that the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/ws_burst_gate_client.py`.

   ```python
   """Burst client for the WS gate. One pre-connected set. No cancel. No drain."""

   from __future__ import annotations

   import argparse
   import asyncio
   import json
   import statistics
   import time
   from pathlib import Path

   import websockets


   def pstats(values: list[float]) -> dict:
       if not values:
           return {"count": 0, "p50": None, "p95": None, "max": None, "min": None}
       ordered = sorted(values)
       return {
           "count": len(ordered),
           "p50": statistics.median(ordered),
           "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
           "max": max(ordered),
           "min": min(ordered),
       }


   async def open_call(url: str, profile: str | None, timeout_s: float) -> dict:
       t0 = time.perf_counter()
       ws = None
       try:
           ws = await websockets.connect(url, max_size=2**24, open_timeout=timeout_s)
           await ws.send(json.dumps({"type": "start", "voice": profile}))
           message = json.loads(await asyncio.wait_for(ws.recv(), timeout_s))
           if message.get("event") != "started":
               await ws.close()
               return {"error": "start:%s" % message}
           return {"ws": ws, "connect_ms": (time.perf_counter() - t0) * 1000.0}
       except Exception as exc:
           if ws is not None:
               try:
                   await ws.close()
               except Exception:
                   pass
           return {"error": str(exc)}


   async def one_call(connection: dict, text: str, timeout_s: float) -> dict:
       ws = connection["ws"]
       t_send = time.perf_counter()
       first = None
       try:
           await ws.send(json.dumps({
               "type": "text",
               "text": text,
               "first_only": True,
               "sent_ns": time.time_ns(),
           }))
           while True:
               message = await asyncio.wait_for(ws.recv(), timeout_s)
               if isinstance(message, (bytes, bytearray)):
                   if first is None:
                       first = time.perf_counter()
                   continue
               event = json.loads(message)
               name = event.get("event")
               if name == "chunk_done":
                   break
               if name == "error":
                   return {"error": event.get("detail")}
           if first is None:
               return {"error": "no_audio"}
           return {"send_to_first_byte_ms": (first - t_send) * 1000.0}
       except Exception as exc:
           return {"error": str(exc)}


   async def burst(live: list[dict], text: str, timeout_s: float) -> dict:
       barrier = asyncio.Event()

       async def task(connection: dict) -> dict:
           await barrier.wait()
           return await one_call(connection, text, timeout_s)

       tasks = [asyncio.create_task(task(connection)) for connection in live]
       barrier.set()
       results = await asyncio.gather(*tasks, return_exceptions=True)
       values = []
       errors = 0
       for result in results:
           if (
               isinstance(result, BaseException)
               or not isinstance(result, dict)
               or result.get("error")
               or result.get("send_to_first_byte_ms") is None
           ):
               errors += 1
               continue
           values.append(result["send_to_first_byte_ms"])
       return {"first_byte": pstats(values), "errors": errors}


   async def run(args) -> dict:
       raw = args.url.rstrip("/")
       if raw.startswith("https://"):
           url = "wss://" + raw[len("https://"):]
       elif raw.startswith("http://"):
           url = "ws://" + raw[len("http://"):]
       elif raw.startswith("ws://") or raw.startswith("wss://"):
           url = raw
       else:
           url = "ws://" + raw
       if not url.endswith("/ws/tts"):
           url = url + "/ws/tts"
       connections = await asyncio.gather(
           *[open_call(url, args.profile, args.timeout) for _ in range(args.b)]
       )
       live = [item for item in connections if item.get("ws") is not None]
       connect_fail = len(connections) - len(live)
       runs = []
       try:
           for index in range(args.warmups + args.repeats):
               result = await burst(live, args.text, args.timeout)
               result["warmup"] = index < args.warmups
               result["rep"] = index
               runs.append(result)
       finally:
           for item in live:
               try:
                   await asyncio.wait_for(item["ws"].close(), timeout=5.0)
               except Exception:
                   pass
       warm = [item for item in runs if not item["warmup"]]
       p50s = [item["first_byte"]["p50"] for item in warm if item["first_byte"]["p50"] is not None]
       p95s = [item["first_byte"]["p95"] for item in warm if item["first_byte"]["p95"] is not None]
       return {
           "b": args.b,
           "runs": runs,
           "warm_runs": warm,
           "p50_of_p50": statistics.median(p50s) if p50s else None,
           "median_p95": statistics.median(p95s) if p95s else None,
           "p95_of_p95": max(p95s) if p95s else None,
           "errors": sum(item["errors"] for item in runs) + connect_fail,
           "connect_fail": connect_fail,
           "rows": args.b * (args.warmups + args.repeats),
       }


   def main() -> None:
       parser = argparse.ArgumentParser()
       parser.add_argument("--url", required=True)
       parser.add_argument("--b", type=int, default=224)
       parser.add_argument("--repeats", type=int, default=4)
       parser.add_argument("--warmups", type=int, default=2)
       parser.add_argument("--text", default="Hello, can you hear me clearly right now?")
       parser.add_argument("--profile", default=None)
       parser.add_argument("--timeout", type=float, default=120.0)
       parser.add_argument("--out", required=True)
       args = parser.parse_args()
       out = asyncio.run(run(args))
       path = Path(args.out)
       path.parent.mkdir(parents=True, exist_ok=True)
       path.write_text(json.dumps(out, indent=2), encoding="utf-8")
       print(json.dumps({"b": args.b, "p95": out["p95_of_p95"], "errors": out["errors"]}))


   if __name__ == "__main__":
       main()
   ```
verify: `python -m py_compile Code/probes/ws_burst_gate_client.py`
expect: exit code 0
if_fail: Open `Code/probes/ws_burst_gate_client.py`. Compare it to the code block in step 1. Run `verify:` again.
result: exit code 0

### T002: Point the probe at the dedicated client
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
context: The probe must call the new client and hash it. Do not edit the client file.
do:
- [x] 1. EDIT `Code/probes/probe_ws_burst_gate.py`: find `sys.executable, str(ROOT / "Code/probes/call_load_client.py"),` and replace it with `sys.executable, str(ROOT / "Code/probes/ws_burst_gate_client.py"),`.
- [x] 2. EDIT `Code/probes/probe_ws_burst_gate.py`: find `                "--url", base, "--mode", "burst", "--b", str(batch),` and replace it with `                "--url", base, "--b", str(batch),`.
- [x] 3. EDIT `Code/probes/probe_ws_burst_gate.py`: find `hashlib.sha256((ROOT / "Code/probes/call_load_client.py").read_bytes()).hexdigest()` and replace it with `hashlib.sha256((ROOT / "Code/probes/ws_burst_gate_client.py").read_bytes()).hexdigest()`.
- [x] 4. RUN `python -m py_compile Code/probes/probe_ws_burst_gate.py`.
verify: `python -m py_compile Code/probes/probe_ws_burst_gate.py`
expect: exit code 0
if_fail: Open the probe. Check the three replaced lines. Run `verify:` again.
result: exit code 0

### T003: Fix the client barrier and run the gate
status: DONE
blocked_reason:
file: Code/probes/probe_ws_burst_gate.py
also_edit: Code/probes/ws_burst_gate_client.py; Code/probes/out/ws_burst_gate/
context: The client waits on a barrier that never opens. No text is sent. Add barrier.set() after the tasks start. Then run. The T4 must be free.
do:
- [x] 1. EDIT `Code/probes/ws_burst_gate_client.py`: find the block below and replace it with the replacement block below.
- [x] 2. RUN `python -m py_compile Code/probes/ws_burst_gate_client.py`.
- [x] 3. RUN `rm -f Code/probes/out/ws_burst_gate/gate.json Code/probes/out/ws_burst_gate/burst_224.json Code/probes/out/ws_burst_gate/burst_320.json`.
- [x] 4. RUN `timeout 1800 python Code/probes/probe_ws_burst_gate.py`.
- [x] 5. CHECK that the final line is JSON with the key `gate_224`.

   Find this block:

   ```python
       results = await asyncio.gather(
           *[asyncio.create_task(task(connection)) for connection in live],
           return_exceptions=True,
       )
   ```

   Replace it with this block:

   ```python
       tasks = [asyncio.create_task(task(connection)) for connection in live]
       barrier.set()
       results = await asyncio.gather(*tasks, return_exceptions=True)
   ```
verify: `python -c "import json,hashlib,pathlib; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); p=pathlib.Path('Code/probes/probe_ws_burst_gate.py'); c=pathlib.Path('Code/probes/ws_burst_gate_client.py'); print(len(d['rows']), d['probe_sha256']==hashlib.sha256(p.read_bytes()).hexdigest(), d['client_sha256']==hashlib.sha256(c.read_bytes()).hexdigest(), 'per_rep' not in d['rows'][0])"`
expect: 2 True True True
if_fail: Run `nvidia-smi`. If the client does not compile, compare step 1. If no text is sent, check the `barrier.set()` line. Run steps 3 and 4 again. If it fails twice, set status BLOCKED.
result: 2 True True True

### T004: Create the corrected run report
status: DONE
blocked_reason:
file: .stageset/runs/20261122-230000-RUN.md
context: This is attempt 3. Use the real values from gate.json. Do not invent values. Attempts 1 and 2 are not valid.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors']} for r in d['rows']})"`.
- [x] 2. CREATE `.stageset/runs/20261122-230000-RUN.md` with the block below.
- [x] 3. EDIT `.stageset/runs/20261122-230000-RUN.md`: replace `<TABLE>` with the output of step 1.
- [x] 4. EDIT `.stageset/runs/20261122-230000-RUN.md`: replace `<RESULT>` with `PASS` if the 224 entry has `errors` 0 and `p95` <= 350. Else replace it with `FAIL`.
- [x] 5. CHECK that no file in `.stageset/runs/` ends with `.reserve`.

   ```markdown
   ---
   id: 20261122-230000-RUN
   type: PROBE
   time: 2026-11-22T23:00:00+05:30
   result: <RESULT>
   skeleton: Skeletons/Probes/probe_ws_burst_gate.md
   check_id: CHECK-WS-GATE-02
   attempt: 3
   spec_revision: 3
   command: "python Code/probes/probe_ws_burst_gate.py"
   ---

   # Run report

   ## Goal

   Prove the first-sound gate on the real WebSocket path at the default call config. This is attempt 3. Attempt 1 (`20261122-210000-RUN`) edited the shared client and is not used. Attempt 2 (`SSLD-031`) is blocked and not used.

   ## Commands

   ```text
   python Code/probes/probe_ws_burst_gate.py
   ```

   ## Observed output (trimmed)

   Full rows: `Code/probes/out/ws_burst_gate/gate.json`. Gate table: <TABLE>.

   The output has `probe_sha256` and `client_sha256`. Both match the files on disk. The client opens one pre-connected set. It does not send `cancel` between runs. It does not call `drain()`. Warmups are not in the p95.

   ## Result

   <RESULT>

   ## Facts

   Gate table: <TABLE>. The clock starts at text send and stops at the first audio byte. The server starts once per B run.

   ## Guesses

   None.

   ## Assumptions checked

   - Consecutive `text` messages on one started WebSocket need no `start`.
   - `sentence` sends raw frames with no pause compression.

   ## Tried

   One fresh server. Two B values. 2 warmups and 4 measured burst repetitions per B.

   ## Open question for planner

   Is B=224 `sentence` a stable end-to-end operating point? Does B=320 stay above 350 ms?

   ## Attempt diff

   Attempt 3 uses a dedicated client with no `cancel` and no `drain`. No app code change.

   ## Smallest repro

   `python Code/probes/probe_ws_burst_gate.py`
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/runs/20261122-230000-RUN.md').read_text(); print('<RESULT>' not in s, '<TABLE>' not in s, 'attempt: 3' in s)"`
expect: True True True
if_fail: Open the run report. Replace `<RESULT>` and `<TABLE>`. Run `verify:` again.
result: True True True

### T005: Create the coding event
status: DONE
blocked_reason:
file: .stageset/sessions/coding-ssld-032-gate-client.md
context: Record one CODING event for the dedicated client and the corrected run. Use the real current time.
do:
- [x] 1. RUN `date +%Y-%m-%dT%H:%M:%S%:z`.
- [x] 2. CREATE `.stageset/sessions/coding-ssld-032-gate-client.md` with the block below.
- [x] 3. EDIT `.stageset/sessions/coding-ssld-032-gate-client.md`: replace `<TIME>` with the output of step 1.

   ```markdown
   ---
   type: CODING
   time: <TIME>
   summary: Add the dedicated gate client and run the corrected WS gate.
   paths: Code/probes/ws_burst_gate_client.py; Code/probes/probe_ws_burst_gate.py; Code/probes/out/ws_burst_gate/gate.json; .stageset/runs/20261122-230000-RUN.md; Skeletons/Probes/probe_ws_burst_gate.md
   related: IDEA-0008; SSLD-031; SSLD-032; 20261122-230000-RUN
   commit: -
   remote: -
   branch: -
   ---

   # Session notes

   ## Decisions

   - Use a dedicated client with no `cancel` and no `drain`.
   - Bind the output with SHA-256.

   ## Outcomes

   - The corrected gate table is in `20261122-230000-RUN`.

   ## Follow-up

   - Planner locks B=224 if the gate passes. Inspect the phase gap if it fails.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/sessions/coding-ssld-032-gate-client.md').read_text(); print('<TIME>' not in s, 'type: CODING' in s)"`
expect: True True
if_fail: Open the event. Replace `<TIME>` with the real time. Run `verify:` again.
result: True True

### T006: Update the probe skeleton metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_ws_burst_gate.md
context: The probe now implements revision 3 with the dedicated client. The corrected run resolves the block.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset implemented_revision: 1` and replace it with `@stageset implemented_revision: 3`.
- [x] 2. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset status: READY` and replace it with `@stageset status: DONE`.
- [x] 3. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset implemented_in: .stageset/sessions/coding-ssld-030-ws-burst-gate.md` and replace it with `@stageset implemented_in: .stageset/sessions/coding-ssld-032-gate-client.md`.
- [x] 4. EDIT `Skeletons/Probes/probe_ws_burst_gate.md`: find `@stageset resolution_of: -` and replace it with `@stageset resolution_of: 20261122-230000-RUN`.
verify: `python -c "import re,pathlib; s=pathlib.Path('Skeletons/Probes/probe_ws_burst_gate.md').read_text(); print(re.search(r'@stageset implemented_revision: (\d+)', s).group(1), re.search(r'@stageset status: (\w+)', s).group(1), re.search(r'@stageset resolution_of: (\S+)', s).group(1))"`
expect: 3 DONE 20261122-230000-RUN
if_fail: Open the skeleton. Fix the four metadata lines. Run `verify:` again.
result: 3 DONE 20261122-230000-RUN

### T007: Correct the idea record
status: DONE
blocked_reason:
file: Ideas/IDEA-0008-natural-live-call-streaming.md
context: The old Phase 5 section uses deviated data. Mark it and append the corrected section with the real values.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print({r['b']: {'p50': r['p50_of_p50'], 'p95': r['p95_of_p95'], 'errors': r['errors']} for r in d['rows']})"`.
- [x] 2. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: find `## Phase 5 WS gate` and replace it with `## Phase 5 WS gate (deviated attempt)`.
- [x] 3. APPEND to `Ideas/IDEA-0008-natural-live-call-streaming.md` the block below.
- [x] 4. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<TABLE>` with the output of step 1.
- [x] 5. EDIT `Ideas/IDEA-0008-natural-live-call-streaming.md`: replace `<DECISION>` with `B=224 sentence is the locked operating point.` if the 224 entry has `errors` 0 and `p95` <= 350. Else replace it with `B=224 sentence is not yet locked. Inspect the phase gap.`.

   ```markdown

   ## Phase 5 WS gate (corrected)

   `20261122-230000-RUN` is the valid attempt. It uses a dedicated client with
   no `cancel` and no `drain`, and SHA-256 bound output. Attempts 1 and 2 are not used.
   Table: <TABLE>.

   Decision: <DECISION>

   B=320 stays a measurement point. Do not set it as a target without a new
   formation or admission change.
   ```
verify: `python -c "import pathlib; s=pathlib.Path('Ideas/IDEA-0008-natural-live-call-streaming.md').read_text(); print(s.count('## Phase 5 WS gate (corrected)'), '<DECISION>' not in s, '<TABLE>' not in s)"`
expect: 1 True True
if_fail: Open the idea file. Fix the heading, the table, or the decision. Run `verify:` again.
result: 1 True True

### T008: Record the corrected fact
status: DONE
blocked_reason:
file: .stageset/facts.md
context: Add one fact row from the corrected run. Use the real values. Do not change old rows.
do:
- [x] 1. RUN `python -c "import json; d=json.load(open('Code/probes/out/ws_burst_gate/gate.json')); print('; '.join('%d ms p50 %.2f p95 %.2f errors %d' % (r['b'], r['p50_of_p50'], r['p95_of_p95'], r['errors']) for r in d['rows']))"`.
- [x] 2. APPEND to `.stageset/facts.md` the row below.
- [x] 3. EDIT `.stageset/facts.md`: replace `<TABLE>` with the output of step 1.

   ```markdown
   | FACT-0157 | 2026-11-22 | Real WS burst gate, dedicated client, one pre-connected set, 2 warmups and 4 measured reps, `sentence` raw frames, default `BATCH_TARGET=32`, SHA-256 bound output: <TABLE>. Attempts 1 and 2 are not used. | Project | CURRENT | `.stageset/runs/20261122-230000-RUN.md` |
   ```
verify: `python -c "import pathlib; s=pathlib.Path('.stageset/facts.md').read_text(); print(s.count('FACT-0157'), '<TABLE>' not in s)"`
expect: 1 True
if_fail: Open `facts.md`. Fix the FACT-0157 row and the `<TABLE>` value. Run `verify:` again.
result: 1 True

### T009: Sync and validate
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
