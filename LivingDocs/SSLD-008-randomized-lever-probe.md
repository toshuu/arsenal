<!-- ss-living-doc v1 -->
# SSLD-008: Randomized lever probe

## STATE
doc_id: SSLD-008
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: Skeletons/Probes/probe_prefill_random.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-008-randomized-lever-probe.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-008-randomized-lever-probe.md --sync

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

## TASKS

### T001: Create the randomized probe
status: DONE
blocked_reason:
file: Code/probes/probe_prefill_random.py
context: Run the harness in random order with 3 bursts. Write one merged JSON with the GPU name and the seed.
do:
- [x] 1. CREATE `Code/probes/probe_prefill_random.py` with the code block below.

   ```python
   """Random-order version of the Phase C lever probe.

   Run: python Code/probes/probe_prefill_random.py
   Writes: Code/probes/out/probe_prefill_random.json
   """

   import json
   import random
   import subprocess
   import sys
   from pathlib import Path

   REPO = Path(__file__).resolve().parents[2]
   OUT = REPO / "Code" / "probes" / "out"
   BENCH = REPO / "Code" / "probes" / "bench_batch_server.py"
   COMBOS = [(v, c) for v in (6.5, 4.0, 3.0, 2.0) for c in (50, 24, 16)]
   SEED = 7
   BURSTS = 3


   def main() -> int:
       OUT.mkdir(parents=True, exist_ok=True)
       order = COMBOS[:]
       random.Random(SEED).shuffle(order)
       rows = []
       gpu = ""
       for voice_seconds, first_tokens in order:
           out = OUT / f"rand_v{voice_seconds}_c{first_tokens}.json"
           cmd = [
               sys.executable, str(BENCH),
               "--bs", "96,128", "--max-b", "128", "--bursts", str(BURSTS), "--warmup", "1",
               "--parity-b", "0", "--fp16",
               "--voice-seconds", str(voice_seconds),
               "--first-tokens", str(first_tokens),
               "--out", str(out),
           ]
           subprocess.run(cmd, check=True, cwd=REPO)
           data = json.loads(out.read_text())
           gpu = data.get("gpu_name") or data.get("device", "")
           for item in data["results"]:
               s = item["summary"]
               rows.append(
                   {
                       "voice_seconds": voice_seconds,
                       "first_tokens": first_tokens,
                       "batch": item["batch"],
                       "p50_ms": s["ttfa_p50_ms"],
                       "p95_ms": s["ttfa_p95_ms"],
                       "under_350": s["under_350"],
                       "samples": s["ttfa_samples"],
                       "rtf": s["rtf_median"],
                       "vram_mb": s["peak_allocated_mb"],
                   }
               )
       agg = {
           "probe": "probe_prefill_random",
           "gpu_name": gpu,
           "seed": SEED,
           "bursts": BURSTS,
           "results": rows,
       }
       path = OUT / "probe_prefill_random.json"
       path.write_text(json.dumps(agg, indent=2) + "\n")
       print("PREFILL_RANDOM_DONE")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/probe_prefill_random.py`.

verify: `python -m py_compile Code/probes/probe_prefill_random.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T002: Run the randomized probe
status: DONE
blocked_reason:
file: Code/probes/probe_prefill_random.py
context: This run is long. It writes 12 harness JSON files and one merged JSON. Do not change any file during the run.
do:
- [x] 1. RUN `python Code/probes/probe_prefill_random.py`.
- [x] 2. CHECK the merged JSON count is 24 and bursts is 3.

verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_prefill_random.json')); print(len(d['results']) == 24 and bool(d['gpu_name']) and d['bursts'] == 3)"`
expect: `True`
if_fail: Read the last harness stdout line. Run `verify:` again. If a CUDA OOM happened, set `status: BLOCKED` and write the batch in `blocked_reason:`.
result: True

### T003: Create the lever picker
status: DONE
blocked_reason:
file: Code/probes/pick_lever.py
context: Pick the lever pair whose p95 is under 350 ms at B=96 and B=128. Break ties with the longer voice.
do:
- [x] 1. CREATE `Code/probes/pick_lever.py` with the code block below.

   ```python
   """Pick one voice and chunk pair from the randomized lever probe.

   Run: python Code/probes/pick_lever.py
   Prints: BEST voice=... cap=... or NO SAFE PAIR
   """

   import json
   from collections import defaultdict
   from pathlib import Path

   REPO = Path(__file__).resolve().parents[2]
   PATH = REPO / "Code" / "probes" / "out" / "probe_prefill_random.json"


   def main() -> int:
       data = json.loads(PATH.read_text())
       groups = defaultdict(dict)
       for row in data["results"]:
           groups[(row["voice_seconds"], row["first_tokens"])][row["batch"]] = row
       candidates = []
       for (voice, cap), by_batch in groups.items():
           if 96 not in by_batch or 128 not in by_batch:
               continue
           a, b = by_batch[96], by_batch[128]
           fa = a["under_350"] / a["samples"]
           fb = b["under_350"] / b["samples"]
           if a["p95_ms"] < 350 and b["p95_ms"] < 350 and fa >= 0.95 and fb >= 0.95:
               candidates.append((max(a["p95_ms"], b["p95_ms"]), voice, cap, a["p95_ms"], b["p95_ms"]))
       if not candidates:
           print("NO SAFE PAIR")
           return 1
       candidates.sort(key=lambda x: (round(x[0], 1), -x[1]))
       _, voice, cap, p96, p128 = candidates[0]
       print(f"BEST voice={voice} cap={cap} p95_b96={p96} p95_b128={p128}")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/pick_lever.py`.

verify: `python -m py_compile Code/probes/pick_lever.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T004: Pick the lever pair
status: DONE
blocked_reason:
file: Code/probes/pick_lever.py
context: Run the picker on the randomized probe JSON. The output names one voice length and one token cap.
do:
- [x] 1. RUN `python Code/probes/pick_lever.py`.

verify: `python -c "import subprocess,sys; r=subprocess.run([sys.executable,'Code/probes/pick_lever.py'],capture_output=True,text=True); print(r.returncode == 0 and r.stdout.startswith('BEST voice='))"`
expect: `True`
if_fail: Run `python Code/probes/pick_lever.py` and read the line. If it prints `NO SAFE PAIR`, set `status: BLOCKED` and write the best p95 pair in `blocked_reason:`.
result: BEST voice=4.0 cap=16 p95_b96=233.42 p95_b128=247.31

### T005: Close the probe skeleton and record the fact
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_prefill_random.md
also_edit: .stageset/facts.md
context: Set the probe skeleton to DONE. Add one fact with the chosen pair and both p95 values.
do:
- [x] 1. EDIT `@stageset status: READY` to `@stageset status: DONE`.
- [x] 2. EDIT `@stageset implemented_revision: 0` to `@stageset implemented_revision: 1`.
- [x] 3. EDIT `@stageset implemented_in: -` to `@stageset implemented_in: .stageset/sessions/coding-ssld-008-randomized-lever-probe.md`.
- [x] 4. EDIT `@stageset last_updated_in: .stageset/sessions/ideation-phase-c-levers.md` to `@stageset last_updated_in: .stageset/sessions/coding-ssld-008-randomized-lever-probe.md`.
- [x] 5. APPEND one fact row to `.stageset/facts.md` with the `BEST` line from T004 and the GPU name.

verify: `python scripts/stageset-status.py --validate`
expect: `StageSet validation passed.`
if_fail: Read the validation error. Fix only the metadata lines. Run `verify:` again.
result: StageSet validation passed.
