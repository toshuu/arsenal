<!-- ss-living-doc v1 -->
# SSLD-006: Batched burst harness

## STATE
doc_id: SSLD-006
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Probes/bench_batch_server.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-006-batch-harness.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-006-batch-harness.md --sync

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

### T001: Create the burst harness
status: DONE
blocked_reason:
file: Code/probes/bench_batch_server.py
context: This probe measures unique-text lockstep batches on one GPU. It writes only Code/probes/out/.
do:
- [x] 1. CREATE `Code/probes/bench_batch_server.py` with the code block below.
- [x] 2. CHECK that the file has valid Python syntax.

   ```python
   """Burst probe for the Phase B batched streaming server.

   One model copy, one process, one lockstep batch per burst. Measures per-row
   first non-silent latency, wall time, aggregate RTF, and peak VRAM.

   Run from the repository root:
     python Code/probes/bench_batch_server.py --max-b 64 --bursts 3

   Writes Code/probes/out/bench_batch_server.json.
   """

   import argparse
   import json
   import logging
   import os
   import sys
   import time
   from pathlib import Path

   import torch

   REPO = Path(__file__).resolve().parents[2]
   HERE = Path(__file__).resolve().parent
   sys.path.insert(0, str(REPO / "Code"))
   os.chdir(REPO / "Code" / "model")

   logging.disable(logging.CRITICAL)
   from pocket_tts import TTSModel  # noqa: E402

   from batch.batched_stream import BatchedStream  # noqa: E402

   SILENCE_THRESHOLD = 0.01

   SUBJECTS = [
       "The old sailor",
       "A young engineer",
       "The quiet librarian",
       "A careful painter",
       "The tired farmer",
       "A curious student",
       "The local baker",
       "A friendly driver",
   ]
   VERBS = [
       "found",
       "opened",
       "carried",
       "noticed",
       "cleaned",
       "painted",
       "measured",
       "packed",
   ]
   OBJECTS = [
       "a brass key",
       "an old map",
       "a small lantern",
       "a folded letter",
       "a wooden box",
       "a silver coin",
       "a blue notebook",
       "a broken clock",
   ]
   PLACES = [
       "harbor",
       "station",
       "garden",
       "library",
       "workshop",
       "market",
       "courtyard",
       "lighthouse",
   ]


   def make_texts(count: int) -> list[str]:
       texts = []
       for index in range(count):
           subject = SUBJECTS[index % len(SUBJECTS)]
           verb = VERBS[(index // len(SUBJECTS)) % len(VERBS)]
           obj = OBJECTS[(index // 4) % len(OBJECTS)]
           place = PLACES[(index * 3) % len(PLACES)]
           texts.append(
               f"{subject} {verb} {obj} while the wind moved slowly near the "
               f"{place}, and waited for the morning train."
           )
       return texts


   def pct(values: list[float], q: float) -> float | None:
       if not values:
           return None
       ordered = sorted(values)
       pos = (q / 100.0) * (len(ordered) - 1)
       low = int(pos)
       high = min(low + 1, len(ordered) - 1)
       frac = pos - low
       return ordered[low] * (1.0 - frac) + ordered[high] * frac


   def first_sound_ms(audio: torch.Tensor, times: list[float], samples_per_frame: int) -> float | None:
       if audio.numel() == 0 or not times:
           return None
       mono = audio.detach().to("cpu").abs()
       hits = torch.nonzero(mono > SILENCE_THRESHOLD, as_tuple=False)
       if hits.numel() == 0:
           return None
       frame = int(hits[0].item()) // samples_per_frame
       frame = min(frame, len(times) - 1)
       return times[frame] * 1000.0


   def main() -> int:
       parser = argparse.ArgumentParser()
       parser.add_argument("--bs", default="1,4,8,12,16,24,32,40,48,64")
       parser.add_argument("--max-b", type=int, default=64)
       parser.add_argument("--bursts", type=int, default=3)
       parser.add_argument("--warmup", type=int, default=1)
       parser.add_argument("--frames", type=int, default=0, help="0 uses the module default")
       parser.add_argument("--temp", type=float, default=0.3)
       parser.add_argument("--parity-b", type=int, default=32)
       parser.add_argument("--parity-frames", type=int, default=32)
       parser.add_argument("--voice", default=str(HERE / "ref" / "voice.wav"))
       parser.add_argument("--out", default=str(HERE / "out" / "bench_batch_server.json"))
       args = parser.parse_args()

       batches = [int(x) for x in args.bs.split(",") if x.strip()]
       batches = [b for b in batches if 0 < b <= args.max_b]
       if not batches:
           print("no batch sizes to run")
           return 1

       out_path = Path(args.out)
       if not out_path.is_absolute():
           out_path = REPO / out_path

       model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
       model.temp = args.temp
       stream = BatchedStream(model, args.voice)
       samples_per_frame = int(round(model.config.mimi.sample_rate / model.mimi.frame_rate))
       texts = make_texts(max(batches))

       for _ in range(args.warmup):
           stream.stream(texts[: min(4, len(texts))], max_frames=8)
       torch.cuda.synchronize()

       parity = None
       if args.parity_b and args.parity_b <= len(texts):
           model.temp = 0.0
           single = stream.stream([texts[0]], max_frames=args.parity_frames)[0]
           batched = stream.stream(texts[: args.parity_b], max_frames=args.parity_frames)[0]
           limit = min(single.numel(), batched.numel())
           single = single[:limit]
           batched = batched[:limit]
           diff = float((single - batched).abs().max())
           corr = None
           if single.std() > 0 and batched.std() > 0:
               corr = float(torch.corrcoef(torch.stack([single, batched]))[0, 1])
           parity = {
               "batch": args.parity_b,
               "frames": args.parity_frames,
               "max_abs_diff": diff,
               "corr": corr,
           }
           model.temp = args.temp

       results = []
       for batch_size in batches:
           torch.cuda.reset_peak_memory_stats()
           bursts = []
           errors = []
           for burst in range(args.bursts):
               offset = burst * 7
               batch_texts = [
                   texts[(offset + row) % len(texts)] for row in range(batch_size)
               ]
               frame_times: list[list[float]] = [[] for _ in range(batch_size)]
               frame_no = [0] * batch_size
               t_start = time.perf_counter()

               def on_chunk(row, chunk, elapsed):
                   if row == 0 and frame_no[row] < 5:
                       torch.cuda.synchronize()
                   frame_times[row].append(time.perf_counter() - t_start)
                   frame_no[row] += 1

               try:
                   audio = stream.stream(
                       batch_texts,
                       on_chunk=on_chunk,
                       max_frames=args.frames or None,
                   )
                   torch.cuda.synchronize()
                   wall_s = time.perf_counter() - t_start
               except torch.cuda.OutOfMemoryError:
                   errors.append(f"batch {batch_size} burst {burst}: CUDA OOM")
                   torch.cuda.empty_cache()
                   break
               except RuntimeError as exc:
                   if "out of memory" not in str(exc).lower():
                       raise
                   errors.append(f"batch {batch_size} burst {burst}: {exc}")
                   torch.cuda.empty_cache()
                   break

               first_ms = [
                   first_sound_ms(audio[row], frame_times[row], samples_per_frame)
                   for row in range(batch_size)
               ]
               audio_s = sum(row.numel() for row in audio) / model.config.mimi.sample_rate
               bursts.append(
                   {
                       "wall_s": round(wall_s, 4),
                       "audio_s": round(audio_s, 4),
                       "rtf": round(wall_s / audio_s, 4) if audio_s > 0 else None,
                       "x_realtime": round(audio_s / wall_s, 3) if wall_s > 0 else None,
                       "first_ms": [round(x, 2) if x is not None else None for x in first_ms],
                   }
               )

           all_first = [x for burst in bursts for x in burst["first_ms"] if x is not None]
           walls = [burst["wall_s"] for burst in bursts]
           audio_s = [burst["audio_s"] for burst in bursts]
           rtfs = [burst["rtf"] for burst in bursts if burst["rtf"] is not None]
           summary = {
               "batch": batch_size,
               "bursts": len(bursts),
               "ttfa_p50_ms": round(pct(all_first, 50), 2) if all_first else None,
               "ttfa_p95_ms": round(pct(all_first, 95), 2) if all_first else None,
               "ttfa_max_ms": round(max(all_first), 2) if all_first else None,
               "ttfa_samples": len(all_first),
               "under_350": sum(1 for x in all_first if x <= 350),
               "under_350_fraction": round(sum(1 for x in all_first if x <= 350) / len(all_first), 4)
               if all_first
               else None,
               "wall_s_median": round(pct(walls, 50), 3) if walls else None,
               "audio_s_median": round(pct(audio_s, 50), 3) if audio_s else None,
               "rtf_median": round(pct(rtfs, 50), 4) if rtfs else None,
               "x_realtime_median": round(1.0 / pct(rtfs, 50), 3)
               if rtfs and pct(rtfs, 50)
               else None,
               "peak_allocated_mb": round(torch.cuda.max_memory_allocated() / 1e6, 1),
               "errors": errors,
           }
           results.append({"batch": batch_size, "summary": summary, "bursts": bursts})
           if errors:
               break

       output = {
           "probe": "bench_batch_server",
           "device": torch.cuda.get_device_name(0),
           "torch": torch.__version__,
           "cuda": torch.version.cuda,
           "voice": str(args.voice),
           "temp": args.temp,
           "silence_threshold": SILENCE_THRESHOLD,
           "bursts_requested": args.bursts,
           "frames": args.frames,
           "parity": parity,
           "results": results,
       }
       out_path.parent.mkdir(parents=True, exist_ok=True)
       out_path.write_text(json.dumps(output, indent=2) + "\n")

       print(" B   p50    p95    max  under350   wall_s  audio_s   RTF   xRT   MB")
       for item in results:
           s = item["summary"]
           print(
               f"{s['batch']:3d} {s['ttfa_p50_ms'] or 0:6.1f} {s['ttfa_p95_ms'] or 0:6.1f} "
               f"{s['ttfa_max_ms'] or 0:6.1f} {s['under_350']:>3}/{s['ttfa_samples']:<3} "
               f"{s['wall_s_median'] or 0:8.2f} {s['audio_s_median'] or 0:8.2f} "
               f"{s['rtf_median'] or 0:7.3f} {s['x_realtime_median'] or 0:6.2f} "
               f"{s['peak_allocated_mb']:6.0f}"
           )
           if s["errors"]:
               print("  errors:", "; ".join(s["errors"]))
       if parity is not None:
           print(
               f"parity B={parity['batch']} frames={parity['frames']} "
               f"maxdiff={parity['max_abs_diff']:.6f} corr={parity['corr']}"
           )
       print("BENCH_BATCH_SERVER_DONE")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```
verify: `python -m py_compile Code/probes/bench_batch_server.py && echo OK`
expect: OK
if_fail: Open `Code/probes/bench_batch_server.py`. Make it match the code block in step 2 exactly. Run `verify:` again.
result: OK
### T002: Run the knee probe
status: DONE
blocked_reason:
file: Code/probes/bench_batch_server.py
context: This runs B=30,32,34,35,36 with 5 bursts each and B=32 parity. It writes the knee JSON.
do:
- [x] 1. RUN `python Code/probes/bench_batch_server.py --bs 30,32,34,35,36 --bursts 5 --parity-b 32 --out Code/probes/out/bench_batch_server_knee.json`.
- [x] 2. CHECK that the command prints `BENCH_BATCH_SERVER_DONE`.
- [x] 3. CHECK that `Code/probes/out/bench_batch_server_knee.json` exists.
verify: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); print(d['probe'])"`
expect: bench_batch_server
if_fail: Read the command output. If CUDA ran out of memory, lower `--bs` and run again. Run `verify:` again.
result: bench_batch_server
### T003: Check B=32 parity
status: DONE
blocked_reason:
file: Code/probes/out/bench_batch_server_knee.json
context: This checks that a B=32 batch row matches a B=1 batch row at temperature 0.
do:
- [x] 1. RUN the verify command.
- [x] 2. CHECK that it prints `True`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); print(d['parity']['max_abs_diff'] < 1e-3)"`
expect: True
if_fail: Read the `parity` object. If the diff is 1e-3 or more, compare `_build_prefixes` and the B=1 path. Run `verify:` again.
result: True
### T004: Check B=32 p95 and tail
status: DONE
blocked_reason:
file: Code/probes/out/bench_batch_server_knee.json
context: This checks the Phase B target at B=32: p95 below 350 ms and at least 95 percent of rows below 350 ms.
do:
- [x] 1. RUN the verify command.
- [x] 2. CHECK that it prints `True`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); s={x['batch']:x['summary'] for x in d['results']}[32]; print(s['ttfa_p95_ms'] < 350 and s['under_350_fraction'] >= 0.95)"`
expect: True
if_fail: Read the B=32 summary. If p95 or the fraction fails, rerun T002 with more bursts. Run `verify:` again.
result: True
### T005: Check B=30 p95
status: DONE
blocked_reason:
file: Code/probes/out/bench_batch_server_knee.json
context: This checks the production-safe batch: B=30 keeps p95 below 350 ms.
do:
- [x] 1. RUN the verify command.
- [x] 2. CHECK that it prints `True`.
verify: `python -c "import json; d=json.load(open('Code/probes/out/bench_batch_server_knee.json')); s={x['batch']:x['summary'] for x in d['results']}[30]; print(s['ttfa_p95_ms'] < 350)"`
expect: True
if_fail: Read the B=30 summary. If p95 is 350 or more, rerun T002 with more bursts. Run `verify:` again.
result: True
### T006: Update probe metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/bench_batch_server.md
context: The probe and checks are done. This task records that the probe implements spec_revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/bench_batch_server.md`: replace `status: READY` with `status: DONE`.
- [x] 2. EDIT `Skeletons/Probes/bench_batch_server.md`: replace `implemented_revision: 0` with `implemented_revision: 1`.
- [x] 3. EDIT `Skeletons/Probes/bench_batch_server.md`: replace `implemented_in: -` with `implemented_in: .stageset/sessions/coding-ssld-006-batch-harness.md`.
- [x] 4. EDIT `Skeletons/Probes/bench_batch_server.md`: replace `last_updated_in: .stageset/sessions/ideation-batch-server.md` with `last_updated_in: .stageset/sessions/coding-ssld-006-batch-harness.md`.
verify: `python -c "s=open('Skeletons/Probes/bench_batch_server.md').read(); print('OK' if all(x in s for x in ['implemented_revision: 1','status: DONE','implemented_in: .stageset/sessions/coding-ssld-006-batch-harness.md','last_updated_in: .stageset/sessions/coding-ssld-006-batch-harness.md']) else 'FAIL')"`
expect: OK
if_fail: Open `Skeletons/Probes/bench_batch_server.md`. Make the four replacements from steps 1 to 4. Run `verify:` again.
result: OK