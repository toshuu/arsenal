<!-- ss-living-doc v1 -->
# SSLD-010: GPU-agnostic scheduling optimizations

## STATE
doc_id: SSLD-010
status: BLOCKED
current_task: T005
tasks_done: 4
tasks_total: 6
skeleton: Skeletons/Code/batch/batched_stream.py
spec_revision: 4
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-010-gpu-agnostic-optim.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-010-gpu-agnostic-optim.md --sync

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

### T001: Add length-bucket admission helper
status: DONE
blocked_reason:
file: Code/batch/scheduler.py
context: Add portable batching helper (V11): estimate token length, bucket texts, admit up to max batch per bucket.
do:
- [x] 1. CREATE `Code/batch/scheduler.py` with the code block below.

   ```python
   """Portable batching helpers: bucketing and admission control."""

   from __future__ import annotations

   from dataclasses import dataclass


   @dataclass
   class AdmittedBatch:
       texts: list[str]
       bucket: int
       dropped: int


   def estimate_tokens(text: str) -> int:
       # Cheap portable estimate; replace with tokenizer length when available.
       return max(1, len(text.split()))


   def bucket_texts(texts: list[str], bucket_size: int = 8) -> dict[int, list[str]]:
       buckets: dict[int, list[str]] = {}
       for text in texts:
           n = estimate_tokens(text)
           key = ((n + bucket_size - 1) // bucket_size) * bucket_size
           buckets.setdefault(key, []).append(text)
       return dict(sorted(buckets.items()))


   def admit_batches(texts: list[str], max_batch: int, bucket_size: int = 8) -> list[AdmittedBatch]:
       out: list[AdmittedBatch] = []
       for key, group in bucket_texts(texts, bucket_size=bucket_size).items():
           for i in range(0, len(group), max_batch):
               chunk = group[i : i + max_batch]
               dropped = 0
               out.append(AdmittedBatch(texts=chunk, bucket=key, dropped=dropped))
       return out
   ```

- [x] 2. RUN `python -m py_compile Code/batch/scheduler.py`.

verify: `python -m py_compile Code/batch/scheduler.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read traceback. Fix copied code only. Run `verify:` again.
result: COMPILED COMPILED

### T002: Add pipelined burst probe (CPU prep overlap)
status: DOING
blocked_reason:
file: Code/probes/probe_pipelined_bursts.py
context: V12 portable probe. Prepare next burst texts on CPU thread while GPU runs current burst (sequential GPU, overlapped host prep).
do:
- [x] 1. CREATE `Code/probes/probe_pipelined_bursts.py` with the code block below.

   ```python
   """Pipelined burst probe (CPU prep overlap)."""

   import argparse, json, logging, os, sys, time
   from concurrent.futures import ThreadPoolExecutor
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

   def prep(texts, b, rnd):
       return [texts[(rnd * 13 + r) % len(texts)] for r in range(b)]

   def main():
       ap = argparse.ArgumentParser()
       ap.add_argument("--b", type=int, default=128)
       ap.add_argument("--rounds", type=int, default=10)
       ap.add_argument("--voice", default=str(REPO / "Code/probes/ref/voice.wav"))
       ap.add_argument("--profile", default=str(REPO / "Code/probes/out/voice_4s_cond.pt"))
       ap.add_argument("--out", default=str(REPO / "Code/probes/out/probe_pipelined.json"))
       args = ap.parse_args()
       model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
       enable_fp16_backbone(model); model.temp = 0.3
       sr = model.config.mimi.sample_rate
       spf = int(round(sr / model.mimi.frame_rate))
       texts = make_texts(max(args.b, 160))
       base = BatchedStream(model, voice=args.voice, voice_seconds=4.0, max_first_tokens=16)
       Path(args.profile).parent.mkdir(parents=True, exist_ok=True)
       base.save_voice_profile(args.profile, conditioned=True)
       stream = BatchedStream(model, voice_profile=args.profile, max_first_tokens=16, compact=True)
       stream.stream(texts[:4], max_frames=4); torch.cuda.synchronize()
       all_ms=[]; walls=[]; bursts=[]
       with ThreadPoolExecutor(max_workers=1) as ex:
           fut = ex.submit(prep, texts, args.b, 0)
           for rnd in range(args.rounds):
               bt = fut.result()
               if rnd + 1 < args.rounds:
                   fut = ex.submit(prep, texts, args.b, rnd + 1)
               ft=[[] for _ in range(args.b)]
               t0=time.perf_counter()
               def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
               audio=stream.stream(bt,on_chunk=cb); torch.cuda.synchronize()
               wall=time.perf_counter()-t0; walls.append(wall)
               bms=[first_sound_ms(audio[r],ft[r],spf) for r in range(args.b)]
               bms=[x for x in bms if x is not None]
               bursts.append({"p95": round(pct(bms,95),2), "under": sum(1 for x in bms if x<=350), "n": len(bms)})
               all_ms.extend(bms)
       agg={"B":args.b,"rounds":args.rounds,"p50":round(pct(all_ms,50),2),"p95":round(pct(all_ms,95),2),
            "under":sum(1 for x in all_ms if x<=350),"total":len(all_ms),
            "under_pct":round(100*sum(1 for x in all_ms if x<=350)/len(all_ms),3),"bursts":bursts}
       Path(args.out).parent.mkdir(parents=True, exist_ok=True)
       Path(args.out).write_text(json.dumps(agg, indent=2)+"\n")
       print(json.dumps(agg))
       print("PIPELINED_DONE")
   if __name__ == "__main__":
       main()
   ```

- [x] 2. RUN `python -m py_compile Code/probes/probe_pipelined_bursts.py`.

verify: `python -m py_compile Code/probes/probe_pipelined_bursts.py; echo COMPILED`
expect: `COMPILED`
if_fail: Read traceback. Fix copied code only. Run `verify:` again.
result: COMPILED COMPILED

### T003: Run pipelined probe
status: DONE
blocked_reason:
file: Code/probes/probe_pipelined_bursts.py
context: Measure pipelined burst behavior at B=128 (portable overlap). Record output.
do:
- [x] 1. RUN `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python Code/probes/probe_pipelined_bursts.py --b 128 --rounds 10 --out Code/probes/out/probe_pipelined_b128.json`.

verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_pipelined_b128.json')); print(d['B']==128 and d['rounds']==10 and d['p95'] is not None)"`
expect: `True`
if_fail: Read last stdout/stderr. Run `verify:` again. If GPU OOM, set `status: BLOCKED`.
result: PIPELINED_DONE

### T004: Stable soak B=128
status: DONE
blocked_reason:
file: Code/probes/soak_batch_b160.py
context: Gate D stability follow-up (portable config). Run sustained soak at B=128.
do:
- [x] 1. CREATE `Code/probes/soak_batch.py` (reusable) and ran B=128 soak.
- [x] 2. RUN soak; interrupted by user, partial data salvaged to summary JSON.

verify: `python -c "import json,os; p='Code/probes/out/soak_b128_summary.json'; print(os.path.exists(p))"`
expect: `True`
if_fail: Check script/logs. Run `verify:` again. If runtime exceeds limits, set `status: BLOCKED` with partial data path.
result: PARTIAL 305 bursts 39040 req 99.91% <350 p95_med 226.21 p95_p95 302.22 max 364.49

### T005: Stable soak B=144
status: BLOCKED
blocked_reason: User stopped for time. B=144 soak not run. B=128 partial stable (99.91% <350).
file: Code/probes/soak_batch.py
context: Compare stability at B=144.
do:
- [ ] 1. RUN B=144 soak (15 min) and produce `Code/probes/out/soak_b144_summary.json`.

verify: `python -c "import json,os; p='Code/probes/out/soak_b144_summary.json'; print(os.path.exists(p))"`
expect: `True`
if_fail: Check logs. Run `verify:` again. If blocked, record reason.
result:

### T006: Record facts and close
status: TODO
blocked_reason:
file: .stageset/facts.md
also_edit: Ideas/optimization-strategy.md
context: Record V11/V12 probes and stable-B soak results. Mark doc done.
do:
- [ ] 1. APPEND fact rows for pipelined probe and B=128/B=144 soak results.
- [ ] 2. APPEND short note to `Ideas/optimization-strategy.md` (GPU-agnostic optimizations section).
- [ ] 3. RUN `python scripts/stageset-status.py --sync`.

verify: `python scripts/stageset-status.py --validate`
expect: `StageSet validation passed.`
if_fail: Fix metadata/content issues. Run `verify:` again.
result:
