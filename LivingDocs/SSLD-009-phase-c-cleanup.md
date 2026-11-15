<!-- ss-living-doc v1 -->
# SSLD-009: Phase C cleanup and clean lever probe

## STATE
doc_id: SSLD-009
status: DONE
current_task: T008
tasks_done: 8
tasks_total: 8
skeleton: Skeletons/Code/batch/batched_stream.py
spec_revision: 4
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-009-phase-c-cleanup.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-009-phase-c-cleanup.md --sync

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

### T001: Cut the voice before the pause
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
context: Move the `voice_seconds` cut before `end_on_pause`. Then the prompt ends on a pause. Keep the defaults unchanged.
do:
- [x] 1. EDIT the block below and replace it with the new block.

   ```python
           audio = end_on_pause(audio, self.model.config.mimi.sample_rate)
           if self.voice_seconds is not None:
               limit = int(self.voice_seconds * self.model.config.mimi.sample_rate)
               audio = audio[..., :limit]
   ```

   ```python
           if self.voice_seconds is not None:
               limit = int(self.voice_seconds * self.model.config.mimi.sample_rate)
               audio = audio[..., :limit]
           audio = end_on_pause(audio, self.model.config.mimi.sample_rate)
   ```

- [x] 2. RUN `python -m py_compile Code/batch/batched_stream.py`.

verify: `python -m py_compile Code/batch/batched_stream.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix only this block. Run `verify:` again.
result: COMPILED

### T002: Create the cut-order check
status: DONE
blocked_reason:
file: Code/probes/check_voice_cut_order.py
context: This check reads the source and proves the cut comes before `end_on_pause`.
do:
- [x] 1. CREATE `Code/probes/check_voice_cut_order.py` with the code block below.

   ```python
   """Check that the voice cut comes before end_on_pause.

   Run: python Code/probes/check_voice_cut_order.py
   Prints: CHECK_VOICE_CUT_ORDER PASS or FAIL
   """

   from pathlib import Path

   REPO = Path(__file__).resolve().parents[2]
   SRC = REPO / "Code" / "batch" / "batched_stream.py"


   def main() -> int:
       text = SRC.read_text()
       cut = text.index("if self.voice_seconds is not None:")
       pause = text.index("audio = end_on_pause(audio, self.model.config.mimi.sample_rate)")
       ok = cut < pause
       print("CHECK_VOICE_CUT_ORDER PASS" if ok else "CHECK_VOICE_CUT_ORDER FAIL")
       print(f"cut_index={cut} pause_index={pause}")
       return 0 if ok else 1


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/check_voice_cut_order.py`.

verify: `python -m py_compile Code/probes/check_voice_cut_order.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T003: Run the cut-order check
status: DONE
blocked_reason:
file: Code/probes/check_voice_cut_order.py
context: Run the check. The cut index must be lower than the pause index.
do:
- [x] 1. RUN `python Code/probes/check_voice_cut_order.py`.

verify: `python Code/probes/check_voice_cut_order.py`
expect: `CHECK_VOICE_CUT_ORDER PASS`
if_fail: Run `verify:` again and read the two indices. Check the edit in T001. If the order is still wrong, set `status: BLOCKED`.
result: CHECK_VOICE_CUT_ORDER PASS

### T004: Create the in-process lever probe
status: DONE
blocked_reason:
file: Code/probes/probe_levers_inproc.py
context: Compare all 12 lever pairs in one process. Interleave rounds in random order. Measure B=96 and B=128.
do:
- [x] 1. CREATE `Code/probes/probe_levers_inproc.py` with the code block below.

   ```python
   """In-process lever comparison.

   Run: python Code/probes/probe_levers_inproc.py
   Writes: Code/probes/out/probe_levers_inproc.json
   """

   import json
   import logging
   import os
   import random
   import sys
   import time
   from pathlib import Path

   import torch

   REPO = Path(__file__).resolve().parents[2]
   sys.path.insert(0, str(REPO / "Code"))
   sys.path.insert(0, str(REPO / "Code" / "probes"))
   os.chdir(REPO / "Code" / "model")
   logging.disable(logging.CRITICAL)

   from pocket_tts import TTSModel  # noqa: E402
   from batch.batched_stream import BatchedStream  # noqa: E402
   from batch.fp16 import enable_fp16_backbone  # noqa: E402
   from bench_batch_server import make_texts, pct, first_sound_ms  # noqa: E402

   VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
   OUT = REPO / "Code" / "probes" / "out" / "probe_levers_inproc.json"
   COMBOS = [(v, c) for v in (6.5, 4.0, 3.0, 2.0) for c in (50, 24, 16)]
   BATCHES = (96, 128)
   SEED = 11
   BURSTS = 3


   def main() -> int:
       model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
       enable_fp16_backbone(model)
       model.temp = 0.3
       sr = model.config.mimi.sample_rate
       spf = int(round(sr / model.mimi.frame_rate))
       texts = make_texts(128)
       streams = {
           cfg: BatchedStream(model, VOICE, voice_seconds=cfg[0], max_first_tokens=cfg[1])
           for cfg in COMBOS
       }
       for stream in streams.values():
           stream.stream(texts[:4], max_frames=4)
       torch.cuda.synchronize()

       rng = random.Random(SEED)
       samples = {cfg: {b: [] for b in BATCHES} for cfg in COMBOS}
       walls = {cfg: {b: [] for b in BATCHES} for cfg in COMBOS}
       audios = {cfg: {b: [] for b in BATCHES} for cfg in COMBOS}
       peaks = {cfg: {b: 0.0 for b in BATCHES} for cfg in COMBOS}

       for rnd in range(BURSTS):
           order = COMBOS[:]
           rng.shuffle(order)
           for cfg in order:
               stream = streams[cfg]
               for b in BATCHES:
                   batch_texts = [texts[(rnd * 7 + r) % len(texts)] for r in range(b)]
                   frame_times = [[] for _ in range(b)]
                   frame_no = [0] * b
                   torch.cuda.reset_peak_memory_stats()
                   t0 = time.perf_counter()

                   def on_chunk(row, chunk, elapsed):
                       frame_times[row].append(time.perf_counter() - t0)
                       frame_no[row] += 1

                   audio = stream.stream(batch_texts, on_chunk=on_chunk)
                   torch.cuda.synchronize()
                   wall = time.perf_counter() - t0
                   for r in range(b):
                       ms = first_sound_ms(audio[r], frame_times[r], spf)
                       if ms is not None:
                           samples[cfg][b].append(ms)
                   audio_s = sum(a.numel() for a in audio) / sr
                   walls[cfg][b].append(wall)
                   audios[cfg][b].append(audio_s)
                   peaks[cfg][b] = max(
                       peaks[cfg][b], float(torch.cuda.max_memory_allocated() / 1e6)
                   )

       rows = []
       for cfg in COMBOS:
           for b in BATCHES:
               s = samples[cfg][b]
               w = pct(walls[cfg][b], 50)
               a = pct(audios[cfg][b], 50)
               rows.append(
                   {
                       "voice_seconds": cfg[0],
                       "first_tokens": cfg[1],
                       "batch": b,
                       "p50_ms": round(pct(s, 50), 2) if s else None,
                       "p95_ms": round(pct(s, 95), 2) if s else None,
                       "under_350": sum(1 for x in s if x <= 350),
                       "samples": len(s),
                       "rtf": round(w / a, 4) if a else None,
                       "vram_mb": round(peaks[cfg][b], 1),
                   }
               )
       agg = {
           "probe": "probe_levers_inproc",
           "gpu_name": torch.cuda.get_device_name(0),
           "seed": SEED,
           "bursts": BURSTS,
           "results": rows,
       }
       OUT.parent.mkdir(parents=True, exist_ok=True)
       OUT.write_text(json.dumps(agg, indent=2) + "\n")
       print("LEVERS_INPROC_DONE")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/probe_levers_inproc.py`.

verify: `python -m py_compile Code/probes/probe_levers_inproc.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T005: Run the in-process probe
status: DONE
blocked_reason: Superseded. In-proc ranking probe biased (FACT-0023). Unbiased 4v3 probe (20261115-205122-RUN, FACT-0028) shows 4.0/16 beats 3.0/16; user accepts 4.0 s.
file: Code/probes/probe_levers_inproc.py
context: This run is long. It uses one model load. Do not change any file during the run.
do:
- [x] 1. RUN `python Code/probes/probe_levers_inproc.py`.
- [x] 2. CHECK the JSON shape and the shorter-voice rule.

verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_levers_inproc.json')); g={(r['voice_seconds'],r['first_tokens'],r['batch']):r['p95_ms'] for r in d['results']}; print(len(d['results']) == 24 and bool(d['gpu_name']) and d['bursts'] == 3 and g[(2.0,16,96)] < g[(4.0,16,96)])"`
expect: `True`
if_fail: Read the last stdout line. Run `verify:` again. If a CUDA OOM happened, set `status: BLOCKED`.
result: False

### T006: Point the picker at the new probe
status: DONE
blocked_reason:
file: Code/probes/pick_lever.py
context: Add a `--path` argument. Keep the same pick rule: p95 under 350 ms at B=96 and B=128, under-350 fraction at least 0.95.
do:
- [x] 1. EDIT the import line `from collections import defaultdict` and add the argparse import above it.

   ```python
   import argparse
   from collections import defaultdict
   ```

- [x] 2. EDIT the line `    data = json.loads(PATH.read_text())` and replace it with the block below.

   ```python
       parser = argparse.ArgumentParser()
       parser.add_argument("--path", default=str(PATH))
       args = parser.parse_args()
       data = json.loads(Path(args.path).read_text())
   ```

- [x] 3. RUN `python -m py_compile Code/probes/pick_lever.py`.

verify: `python -m py_compile Code/probes/pick_lever.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix only the two edits. Run `verify:` again.
result: COMPILED

### T007: Pick the clean operating point
status: DONE
blocked_reason: Resolved by user choice and unbiased probe. Selected: voice 4.0 s, cap 16, B=128 (T4). B=128 p95 372-400 ms 94.4%<350; B=96 p95 264-307 ms 100%<350 (FACT-0028). Phase D/correct KV reuse needed for B=128 margin.
file: Code/probes/pick_lever.py
context: Run the picker on the in-process JSON. Use voice 3.0 s if it passes both batch sizes. Record the choice.
do:
- [x] 1. RUN `python Code/probes/pick_lever.py --path Code/probes/out/probe_levers_inproc.json`.
- [x] 2. CHECK that voice 3.0 s and cap 16 is under 350 ms at B=96 and B=128.
- [x] 3. APPEND one fact row to `.stageset/facts.md` for the selected operating point.
- [x] 4. APPEND a short note to `Ideas/optimization-strategy.md` section 13 with the chosen point.

verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_levers_inproc.json')); g={(r['voice_seconds'],r['first_tokens'],r['batch']):r['p95_ms'] for r in d['results']}; print(g[(3.0,16,96)] < 350 and g[(3.0,16,128)] < 350)"`
expect: `True`
if_fail: Read the p95 values. If 3.0 s fails, set `status: BLOCKED` and write both values in `blocked_reason:`.
result: False
also_edit: .stageset/facts.md; Ideas/optimization-strategy.md

### T008: Close the skeletons
status: DONE
blocked_reason:
file: Skeletons/Code/batch/batched_stream.py
also_edit: Skeletons/Probes/probe_levers_inproc.md
context: Set both skeletons to DONE. Advance `batched_stream` to implemented revision 4.
do:
- [x] 1. EDIT `@stageset status: READY` to `@stageset status: DONE` in `Skeletons/Code/batch/batched_stream.py`.
- [x] 2. EDIT `@stageset implemented_revision: 3` to `@stageset implemented_revision: 4` in `Skeletons/Code/batch/batched_stream.py`.
- [x] 3. EDIT `@stageset implemented_in: .stageset/sessions/coding-ssld-007-prefill-levers.md` to `@stageset implemented_in: .stageset/sessions/coding-ssld-009-phase-c-cleanup.md` in `Skeletons/Code/batch/batched_stream.py`.
- [x] 4. EDIT `@stageset last_updated_in: .stageset/sessions/ideation-phase-c-cleanup.md` to `@stageset last_updated_in: .stageset/sessions/coding-ssld-009-phase-c-cleanup.md` in `Skeletons/Code/batch/batched_stream.py`.
- [x] 5. EDIT `@stageset status: READY` to `@stageset status: DONE` in `Skeletons/Probes/probe_levers_inproc.md`.
- [x] 6. EDIT `@stageset implemented_revision: 0` to `@stageset implemented_revision: 1` in `Skeletons/Probes/probe_levers_inproc.md`.
- [x] 7. EDIT `@stageset implemented_in: -` to `@stageset implemented_in: .stageset/sessions/coding-ssld-009-phase-c-cleanup.md` in `Skeletons/Probes/probe_levers_inproc.md`.

verify: `python scripts/stageset-status.py --validate`
expect: `StageSet validation passed.`
if_fail: Read the validation error. Fix only the metadata lines. Run `verify:` again.
result: StageSet validation passed.
