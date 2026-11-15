<!-- ss-living-doc v1 -->
# SSLD-007: Phase C prefill levers

## STATE
doc_id: SSLD-007
status: DONE
current_task: T009
tasks_done: 9
tasks_total: 9
skeleton: Skeletons/Code/batch/batched_stream.py
spec_revision: 3
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-007-prefill-levers.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-007-prefill-levers.md --sync

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

### T001: Add voice and chunk levers
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
context: Add two optional settings. `voice_seconds` truncates the voice prompt. `max_first_tokens` caps the first text chunk. Defaults must keep current behavior.
do:
- [x] 1. EDIT the constructor line `def __init__(self, model, voice_path: str | Path, max_tokens: int = 50):` and replace it with the line below.

   ```python
   def __init__(self, model, voice_path: str | Path, max_tokens: int = 50, voice_seconds: float | None = None, max_first_tokens: int | None = None):
   ```

- [x] 2. EDIT the line `        self.max_tokens = max_tokens` and replace it with the two lines below.

   ```python
           self.max_tokens = max_tokens
           self.voice_seconds = voice_seconds
           self.max_first_tokens = max_first_tokens
   ```

- [x] 3. EDIT the line `        audio = end_on_pause(audio, self.model.config.mimi.sample_rate)` and replace it with the block below.

   ```python
           audio = end_on_pause(audio, self.model.config.mimi.sample_rate)
           if self.voice_seconds is not None:
               limit = int(self.voice_seconds * self.model.config.mimi.sample_rate)
               audio = audio[..., :limit]
   ```

- [x] 4. EDIT the line `            self.max_tokens,` inside `_first_chunk_text` and replace it with the line below.

   ```python
                   self.max_first_tokens or self.max_tokens,
   ```

- [x] 5. EDIT the line `        return chunks[0] if chunks else text` and replace it with the block below.

   ```python
           first = chunks[0] if chunks else text
           if self.max_first_tokens is None:
               return first
           tokenizer = self.model.flow_lm.conditioner.tokenizer
           ids = tokenizer(first)[0].tolist()
           if len(ids) <= self.max_first_tokens:
               return first
           return tokenizer.decode(ids[: self.max_first_tokens])
   ```

- [x] 6. RUN `python -m py_compile Code/batch/batched_stream.py`.

verify: `python -m py_compile Code/batch/batched_stream.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix only the three edits. Run `verify:` again.
result: COMPILED

### T002: Create the lever check
status: DONE
blocked_reason:
file: Code/probes/check_batch_levers.py
context: This check proves that both knobs work. It loads the model on the GPU and prints one result line.
do:
- [x] 1. CREATE `Code/probes/check_batch_levers.py` with the code block below.

   ```python
   """Check the voice and first-chunk levers.

   Run: python Code/probes/check_batch_levers.py
   Prints: CHECK_BATCH_LEVERS PASS or CHECK_BATCH_LEVERS FAIL
   """

   import logging
   import os
   import sys
   from pathlib import Path

   REPO = Path(__file__).resolve().parents[2]
   sys.path.insert(0, str(REPO / "Code"))
   os.chdir(REPO / "Code" / "model")
   logging.disable(logging.CRITICAL)

   from pocket_tts import TTSModel  # noqa: E402
   from batch.batched_stream import BatchedStream  # noqa: E402

   VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
   TEXT = "The old sailor found a brass key near the harbor, and he waited for the morning train."


   def main() -> int:
       model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
       full = BatchedStream(model, VOICE)
       short = BatchedStream(model, VOICE, voice_seconds=2.0)
       capped = BatchedStream(model, VOICE, max_first_tokens=8)
       full_frames = full.voice.shape[1]
       short_frames = short.voice.shape[1]
       full_chunk = full._first_chunk_text(TEXT)
       cap_chunk = capped._first_chunk_text(TEXT)
       full_tokens = full._text_embedding(full_chunk)[1]
       cap_tokens = full._text_embedding(cap_chunk)[1]
       ok = short_frames < full_frames and cap_tokens < full_tokens
       print("CHECK_BATCH_LEVERS PASS" if ok else "CHECK_BATCH_LEVERS FAIL")
       print(f"voice_frames full={full_frames} short={short_frames}")
       print(f"first_chunk_tokens full={full_tokens} capped={cap_tokens}")
       return 0 if ok else 1


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/check_batch_levers.py`.

verify: `python -m py_compile Code/probes/check_batch_levers.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T003: Run the lever check
status: DONE
blocked_reason:
file: Code/probes/check_batch_levers.py
context: Run the check on the GPU. The short voice must have fewer frames. The capped chunk must have fewer tokens.
do:
- [x] 1. RUN `python Code/probes/check_batch_levers.py`.

verify: `python Code/probes/check_batch_levers.py`
expect: `CHECK_BATCH_LEVERS PASS`
if_fail: Run `python Code/probes/check_batch_levers.py` and read both metric lines. Check that the edits in T001 are present. Then run `verify:` again.
result: CHECK_BATCH_LEVERS PASS

### T004: Add harness flags
status: DONE
blocked_reason:
file: Code/probes/bench_batch_server.py
context: Add `--fp16`, `--voice-seconds`, and `--first-tokens`. Record the GPU name and the config in the JSON.
do:
- [x] 1. EDIT the line `from batch.batched_stream import BatchedStream  # noqa: E402` and replace it with the two lines below.

   ```python
   from batch.batched_stream import BatchedStream  # noqa: E402
   from batch.fp16 import enable_fp16_backbone  # noqa: E402
   ```

- [x] 2. EDIT the line `    parser.add_argument("--out", default=str(HERE / "out" / "bench_batch_server.json"))` and replace it with the four lines below.

   ```python
       parser.add_argument("--out", default=str(HERE / "out" / "bench_batch_server.json"))
       parser.add_argument("--fp16", action="store_true")
       parser.add_argument("--voice-seconds", type=float, default=None)
       parser.add_argument("--first-tokens", type=int, default=None)
   ```

- [x] 3. EDIT the line `    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()` and replace it with the block below.

   ```python
       model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
       if args.fp16:
           enable_fp16_backbone(model)
   ```

- [x] 4. EDIT the line `    stream = BatchedStream(model, args.voice)` and replace it with the line below.

   ```python
       stream = BatchedStream(model, args.voice, voice_seconds=args.voice_seconds, max_first_tokens=args.first_tokens)
   ```

- [x] 5. EDIT the line `        "device": torch.cuda.get_device_name(0),` and replace it with the two lines below.

   ```python
           "device": torch.cuda.get_device_name(0),
           "gpu_name": torch.cuda.get_device_name(0),
           "config": {"fp16": args.fp16, "voice_seconds": args.voice_seconds, "first_tokens": args.first_tokens},
   ```

- [x] 6. RUN `python -m py_compile Code/probes/bench_batch_server.py`.

verify: `python -m py_compile Code/probes/bench_batch_server.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix only the five edits. Run `verify:` again.
result: COMPILED

### T005: Create the prefill lever probe
status: DONE
blocked_reason:
file: Code/probes/probe_prefill_levers.py
context: Run the harness for 12 voice and chunk pairs at B=96 and B=128. Merge the results into one JSON with the GPU name.
do:
- [x] 1. CREATE `Code/probes/probe_prefill_levers.py` with the code block below.

   ```python
   """Measure voice length and first-chunk cap at high batch.

   Run: python Code/probes/probe_prefill_levers.py
   Writes: Code/probes/out/probe_prefill_levers.json
   """

   import json
   import subprocess
   import sys
   from pathlib import Path

   REPO = Path(__file__).resolve().parents[2]
   OUT = REPO / "Code" / "probes" / "out"
   BENCH = REPO / "Code" / "probes" / "bench_batch_server.py"
   COMBOS = [(v, c) for v in (6.5, 4.0, 3.0, 2.0) for c in (50, 24, 16)]


   def main() -> int:
       OUT.mkdir(parents=True, exist_ok=True)
       rows = []
       gpu = ""
       for voice_seconds, first_tokens in COMBOS:
           out = OUT / f"lever_v{voice_seconds}_c{first_tokens}.json"
           cmd = [
               sys.executable, str(BENCH),
               "--bs", "96,128", "--max-b", "128", "--bursts", "2", "--warmup", "1",
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
       agg = {"probe": "probe_prefill_levers", "gpu_name": gpu, "results": rows}
       path = OUT / "probe_prefill_levers.json"
       path.write_text(json.dumps(agg, indent=2) + "\n")
       best = min(rows, key=lambda r: r["p95_ms"])
       print("best", json.dumps(best))
       print("PREFILL_LEVERS_DONE")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/probe_prefill_levers.py`.

verify: `python -m py_compile Code/probes/probe_prefill_levers.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T006: Run the prefill lever probe
status: DONE
blocked_reason:
file: Code/probes/probe_prefill_levers.py
context: This run is long. It writes 12 harness JSON files and one merged JSON. Do not change any file during the run.
do:
- [x] 1. RUN `python Code/probes/probe_prefill_levers.py`.
- [x] 2. CHECK the merged JSON count is 24.

verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_prefill_levers.json')); print(len(d['results']) == 24 and bool(d['gpu_name']))"`
expect: `True`
if_fail: Read the last harness stdout line. Run `verify:` again. If a CUDA OOM happened, set `status: BLOCKED` and write the batch in `blocked_reason:`.
result: True (24 rows, gpu_name Tesla T4)

### T007: Create the lever quality WAV script
status: DONE
blocked_reason:
file: Code/probes/make_lever_quality_wavs.py
context: Generate FP32 and FP16 WAVs for voice lengths 6.5, 3.0, and 2.0 seconds. Use a 24-token first-chunk cap.
do:
- [x] 1. CREATE `Code/probes/make_lever_quality_wavs.py` with the code block below.

   ```python
   """Generate quality WAVs for the voice length lever.

   Run: python Code/probes/make_lever_quality_wavs.py
   Writes: Code/probes/out/lever_quality/*.wav
   """

   import logging
   import os
   import sys
   from pathlib import Path

   import soundfile as sf

   REPO = Path(__file__).resolve().parents[2]
   sys.path.insert(0, str(REPO / "Code"))
   os.chdir(REPO / "Code" / "model")
   logging.disable(logging.CRITICAL)

   from pocket_tts import TTSModel  # noqa: E402
   from batch.batched_stream import BatchedStream  # noqa: E402
   from batch.fp16 import enable_fp16_backbone  # noqa: E402

   VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
   OUT = REPO / "Code" / "probes" / "out" / "lever_quality"
   TEXT = "The quick brown fox jumps over the lazy dog."


   def main() -> int:
       OUT.mkdir(parents=True, exist_ok=True)
       for name, use_fp16 in (("fp32", False), ("fp16", True)):
           model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
           if use_fp16:
               enable_fp16_backbone(model)
           model.temp = 0.0
           for voice_seconds in (6.5, 3.0, 2.0):
               stream = BatchedStream(model, VOICE, voice_seconds=voice_seconds, max_first_tokens=24)
               audio = stream.stream([TEXT])[0].cpu().numpy().reshape(-1)
               path = OUT / f"{name}_voice{voice_seconds}_chunk24.wav"
               sf.write(path, audio, 24000)
               print(path.name, round(len(audio) / 24000, 2))
       print("LEVER_QUALITY_DONE")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

- [x] 2. RUN `python -m py_compile Code/probes/make_lever_quality_wavs.py`.

verify: `python -m py_compile Code/probes/make_lever_quality_wavs.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read the traceback. Fix the copied code only. Run `verify:` again.
result: COMPILED

### T008: Run the lever quality WAV script
status: DONE
blocked_reason:
file: Code/probes/make_lever_quality_wavs.py
context: This writes six WAVs. Listen to them after the run. The longest voice is the reference.
do:
- [x] 1. RUN `python Code/probes/make_lever_quality_wavs.py`.
- [x] 2. CHECK that six WAV files exist.

verify: `python -c "import glob; print(len(glob.glob('Code/probes/out/lever_quality/*.wav')) == 6)"`
expect: `True`
if_fail: Read the last line. Check that `soundfile` is installed. Run `verify:` again.
result: True (6 WAV files)

### T009: Close the skeleton and record facts
status: DONE
blocked_reason:
file: Skeletons/Code/batch/batched_stream.py
also_edit: .stageset/facts.md
context: Set the skeleton to the implemented revision. Add one fact for the probe result. Keep the defaults unchanged.
do:
- [x] 1. EDIT `@stageset status: READY` to `@stageset status: DONE`.
- [x] 2. EDIT `@stageset implemented_revision: 2` to `@stageset implemented_revision: 3`.
- [x] 3. EDIT `@stageset implemented_in: -` to `@stageset implemented_in: .stageset/sessions/coding-ssld-007-prefill-levers.md`.
- [x] 4. EDIT `@stageset last_updated_in: .stageset/sessions/ideation-phase-c-levers.md` to `@stageset last_updated_in: .stageset/sessions/coding-ssld-007-prefill-levers.md`.
- [x] 5. APPEND one fact row to `.stageset/facts.md` with the best p95 from the probe JSON.

verify: `python scripts/stageset-status.py --validate`
expect: `StageSet validation passed.`
if_fail: Read the validation error. Fix only the metadata lines. Run `verify:` again.
result: StageSet validation passed.
