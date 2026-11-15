<!-- ss-living-doc v1 -->
# SSLD-004: T4 GPU baseline

## STATE
doc_id: SSLD-004
status: DONE
current_task: T004
tasks_done: 4
tasks_total: 4
skeleton: Skeletons/Probes/bench_gpu.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-004-gpu-baseline.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-004-gpu-baseline.md --sync

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

### T001: Create bench_gpu.py
status: DONE
blocked_reason:
file: Code/probes/bench_gpu.py
context: The model is in Code/model. The reference voice is in Code/probes/ref. This task creates the read-only GPU probe. Do not run it yet.
do:
- [x] 1. CREATE `Code/probes/bench_gpu.py` with the code block below.
- [x] 2. CHECK that the file has valid Python syntax.

   ```python
   """Read-only GPU baseline probe for pocket-tts-multilingual.

   Writes one JSON file: Code/probes/out/bench_gpu.json.
   Changes no project file except files in Code/probes/out/.
   """
   import argparse
   import copy
   import json
   import math
   import os
   import struct
   import sys
   import time
   import traceback
   import wave
   from pathlib import Path

   import torch

   from pocket_tts import TTSModel

   HERE = Path(__file__).resolve().parent
   MODEL_DIR = HERE.parent / "model"
   OUT_DIR = HERE / "out"
   REF_WAV = HERE / "ref" / "voice.wav"
   TEXT = "Hello, this is a short test sentence."
   SILENCE_THRESHOLD = 0.01


   def pct(values, q):
       if not values:
           return None
       s = sorted(values)
       i = min(len(s) - 1, max(0, int(round((q / 100.0) * (len(s) - 1)))))
       return round(s[i], 3)


   def write_sine_wav(path, seconds=3, rate=24000):
       path.parent.mkdir(parents=True, exist_ok=True)
       with wave.open(str(path), "wb") as handle:
           handle.setnchannels(1)
           handle.setsampwidth(2)
           handle.setframerate(rate)
           frames = bytearray()
           for i in range(seconds * rate):
               value = int(8000 * math.sin(2 * math.pi * 220 * i / rate))
               frames += struct.pack("<h", value)
           handle.writeframes(bytes(frames))


   def main():
       ap = argparse.ArgumentParser()
       ap.add_argument("--runs", type=int, default=20)
       ap.add_argument("--warmup", type=int, default=3)
       ap.add_argument("--device", default="cuda:0")
       ap.add_argument("--text", default=TEXT)
       args = ap.parse_args()

       OUT_DIR.mkdir(parents=True, exist_ok=True)
       start_dir = os.getcwd()
       os.chdir(MODEL_DIR)
       result = {
           "probe": "bench_gpu",
           "device": args.device,
           "text": args.text,
           "runs": args.runs,
           "warmup": args.warmup,
           "silence_threshold": SILENCE_THRESHOLD,
           "errors": [],
       }
       try:
           start = time.perf_counter()
           model = TTSModel.load_model(config="config.yaml")
           result["load_seconds"] = round(time.perf_counter() - start, 3)
           model = model.to(args.device).eval()
           result["device_name"] = (
               torch.cuda.get_device_name(0) if args.device.startswith("cuda") else "cpu"
           )
           result["torch"] = torch.__version__
           result["cuda"] = torch.version.cuda
           result["sample_rate"] = int(model.sample_rate)

           if REF_WAV.exists():
               ref, source = str(REF_WAV), "real"
           else:
               ref_path = OUT_DIR / "ref_synthetic.wav"
               write_sine_wav(ref_path)
               ref, source = str(ref_path), "synthetic"
           result["voice_source"] = source

           start = time.perf_counter()
           state = model.get_state_for_audio_prompt(ref)
           result["voice_prefix_seconds"] = round(time.perf_counter() - start, 4)

           for _ in range(args.warmup):
               for _chunk in model.generate_audio_stream(copy.deepcopy(state), args.text):
                   pass
           torch.cuda.synchronize() if args.device.startswith("cuda") else None
           if args.device.startswith("cuda"):
               torch.cuda.reset_peak_memory_stats()

           rows = []
           for _ in range(args.runs):
               if args.device.startswith("cuda"):
                   torch.cuda.synchronize()
               start = time.perf_counter()
               local_state = copy.deepcopy(state)
               copy_seconds = time.perf_counter() - start

               start = time.perf_counter()
               first_chunk = None
               first_sound = None
               chunk_count = 0
               total_samples = 0
               chunk_samples = []
               for chunk in model.generate_audio_stream(local_state, args.text):
                   now = time.perf_counter() - start
                   if first_chunk is None:
                       first_chunk = now
                   flat = chunk.reshape(-1)
                   if first_sound is None and float(flat.abs().max()) > SILENCE_THRESHOLD:
                       first_sound = now
                   size = int(flat.numel())
                   total_samples += size
                   chunk_count += 1
                   if len(chunk_samples) < 8:
                       chunk_samples.append(size)
               end = time.perf_counter() - start
               audio_seconds = total_samples / float(model.sample_rate)
               rows.append(
                   {
                       "copy_ms": round(copy_seconds * 1000, 3),
                       "first_chunk_ms": round((first_chunk or end) * 1000, 3),
                       "first_sound_ms": round((first_sound or end) * 1000, 3),
                       "end_ms": round(end * 1000, 3),
                       "audio_seconds": round(audio_seconds, 4),
                       "rtf": round(end / audio_seconds, 4) if audio_seconds else None,
                       "chunk_count": chunk_count,
                       "chunk_samples": chunk_samples,
                   }
               )

           first_chunks = [r["first_chunk_ms"] for r in rows]
           first_sounds = [r["first_sound_ms"] for r in rows]
           rtfs = [r["rtf"] for r in rows if r["rtf"] is not None]
           result["runs_data"] = rows
           result["summary"] = {
               "p50_first_chunk_ms": pct(first_chunks, 50),
               "p95_first_chunk_ms": pct(first_chunks, 95),
               "p50_first_sound_ms": pct(first_sounds, 50),
               "p95_first_sound_ms": pct(first_sounds, 95),
               "p50_rtf": pct(rtfs, 50),
               "p95_rtf": pct(rtfs, 95),
               "frames_per_chunk": rows[0]["chunk_samples"] if rows else [],
           }

           start = time.perf_counter()
           audio = model.generate_audio(copy.deepcopy(state), args.text)
           generate_seconds = time.perf_counter() - start
           flat = audio.reshape(-1)
           loud = (flat.abs() > SILENCE_THRESHOLD).nonzero()
           first = int(loud[0]) if len(loud) else None
           duration = float(flat.numel()) / float(model.sample_rate)
           result["full_generate"] = {
               "samples": int(flat.numel()),
               "audio_seconds": round(duration, 3),
               "generate_seconds": round(generate_seconds, 4),
               "rtf": round(generate_seconds / duration, 4) if duration else None,
               "leading_silence_ms": round(first * 1000 / float(model.sample_rate), 1)
               if first is not None
               else None,
           }

           if args.device.startswith("cuda"):
               result["peak_allocated_mb"] = round(torch.cuda.max_memory_allocated() / 1048576, 1)
               result["peak_reserved_mb"] = round(torch.cuda.max_memory_reserved() / 1048576, 1)
           result["param_count"] = sum(p.numel() for p in model.parameters())
           result["param_dtypes"] = sorted({str(p.dtype) for p in model.parameters()})
       except Exception:
           result["errors"].append(traceback.format_exc()[-2000:])
       finally:
           os.chdir(start_dir)

       (OUT_DIR / "bench_gpu.json").write_text(
           json.dumps(result, indent=2, default=str), encoding="utf-8"
       )
       summary = result.get("summary", {})
       print(
           "BENCH_GPU_DONE runs=%d errors=%d p50_ttfa_ms=%s p95_ttfa_ms=%s p50_rtf=%s"
           % (
               args.runs,
               len(result.get("errors", [])),
               summary.get("p50_first_chunk_ms"),
               summary.get("p95_first_chunk_ms"),
               summary.get("p50_rtf"),
           )
       )
       return 0


   if __name__ == "__main__":
       sys.exit(main())
   ```
verify: `python -c "import ast; ast.parse(open('Code/probes/bench_gpu.py').read()); print('syntax ok')"`
expect: syntax ok
if_fail: Open `Code/probes/bench_gpu.py`. Make it match the code block in step 1 exactly. Run `verify:` again.
result: syntax ok

### T002: Run the GPU baseline
status: DONE
blocked_reason:
file: Code/probes/out/bench_gpu.json
context: The script exists. The T4 GPU is on. This task runs 3 warmup streams and 20 measured streams. It needs several minutes.
do:
- [x] 1. RUN `python Code/probes/bench_gpu.py --runs 20 --warmup 3` from the repository root.
- [x] 2. CHECK that the output line starts with `BENCH_GPU_DONE`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/bench_gpu.json')); print(d['runs'], len(d['errors']))"`
expect: 20 0
if_fail: Run the command in step 1 again. If `errors` is not 0, read the first error in `Code/probes/out/bench_gpu.json` and set `blocked_reason:`. Run `verify:` again.
result: 20 0

### T003: Check the GPU summary
status: DONE
blocked_reason:
file: Code/probes/out/bench_gpu.json
context: The benchmark wrote the JSON file. The summary must hold a positive first-chunk time and a positive RTF.
do:
- [x] 1. CHECK that `p50_first_chunk_ms` and `p50_rtf` are above 0.
verify: `python -c "import json; d=json.load(open('Code/probes/out/bench_gpu.json')); print(d['summary']['p50_first_chunk_ms'] > 0 and d['summary']['p50_rtf'] > 0)"`
expect: True
if_fail: Run `python Code/probes/bench_gpu.py --runs 20 --warmup 3` again. Run `verify:` again. If the value is still False, set `blocked_reason:` and STOP.
result: True

### T004: Update skeleton metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/bench_gpu.md
context: The GPU probe ran with no error. This task records that the probe implements spec_revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/bench_gpu.md`: find the text `implemented_revision: 0` and replace it with `implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/bench_gpu.md`: find the text `status: READY` and replace it with `status: DONE`.
verify: `python -c "t=open('Skeletons/Probes/bench_gpu.md').read(); print(t.count('implemented_revision: 1'), t.count('status: DONE'))"`
expect: 1 1
if_fail: Open `Skeletons/Probes/bench_gpu.md`. Make the line with `implemented_revision:` end in 1. Make the line with `status:` end in DONE. Run `verify:` again.
result: 1 1
