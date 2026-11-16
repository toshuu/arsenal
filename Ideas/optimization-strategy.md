---
id: IDEA-0003
title: Final optimization strategy for pocket-tts burst concurrency
status: DISCOVERY
priority: P0
created_in: .stageset/sessions/ideation-pocket-tts-multilingual.md
updated_in: .stageset/sessions/coding-ssld-006-fp16-spike.md
created_at: 2026-11-15T14:30:00+05:30
updated_at: 2026-11-15T18:33:37+05:30
related_ideas: [IDEA-0001, IDEA-0002]
related_reports: [Reports/burst-concurrency-2026-11-15.md]
---

# Final optimization strategy for pocket-tts burst concurrency

Scope: one GPU, T4 first then L4. Streaming on. Unique text per request.
Metric: largest N where p95 TTFA is at most 350 ms, server side.
Hard rule: sustained aggregate RTF must stay below 1.0 at that N.

This file merges IDEA-0002 (measured analysis) with the planner's draft.
IDEA-0002 is the input. This file is the plan.

Every number marked CALC comes from the measured table in IDEA-0002 section 3.
CALC is not a measurement. A prototype must confirm it.

---

## 1. Decision

Do this, in this order:

1. One process, one model, one static batched scheduler. FP32. Target 32 on T4.
2. Remove hot-path CPU work. Target 48.
3. FP16. This is the largest prefill lever. Target 96.
4. Shorter voice prompt and a capped first text chunk. Target 128.
5. RTF work: CUDA graphs, decoder grouping, finished-row masking. Target 160.
6. Repeat on L4. Target 192 to 256.
7. Shared voice KV only if step 6 still needs TTFA headroom. It is not first.

Do not do TensorRT or ONNX now. Ask the owner before that work starts.
Do not do per-row RoPE, continuous batching, or shared voice KV before the
simpler path is measured. They are high-cost and may not raise the ceiling.

### Target table

| Build | T4 p95 <= 350 ms | L4 p95 <= 350 ms | Confidence |
|---|---|---|---|
| Current runtime (measured) | 4 | not measured | high |
| Static batch, FP32 | 32 to 48 | 64 | medium-high |
| + hot-path cleanup | 48 to 64 | 96 | medium |
| + FP16 | 96 to 128 | 160 to 192 | medium |
| + shorter voice + capped first chunk | 128 to 160 | 224 to 256 | medium-low |
| + RTF work (graphs, decode grouping, masking) | 160 to 192 | 256 to 320 | low-medium |
| Sustained RTF limit | about 160 to 200 | about 256 to 320 | to measure |

Commit targets for the SSLDs:

- Phase B: 32 on T4.
- Phase C: 96 on T4.
- Phase D: 128 on T4.
- Phase E: 192 on L4.

The stretch numbers are not promises. The RTF gate decides them.

---

## 2. The binding constraint moves

Do not optimize the wrong thing. Measure both TTFA and RTF at every gate.

| Phase | Binding limit | Lever |
|---|---|---|
| Now | CPU threads. 4 vCPU, 2 threads per request. | One process, one scheduler |
| B | Prefill at high B. CPU at low B. | Batching, buffer reuse |
| C | Prefill share of TTFA (91% at B=64 CALC) | FP16, shorter prefix |
| D | RTF: step + decode against the 80 ms frame | Graphs, decoder grouping, masking |
| E | Host CPU and memory bandwidth | Admission control, L4 |

Key consequence: **shared voice KV is a TTFA-only lever**. It does not improve
step or decode time. If RTF binds at 160, shared KV does not raise N above 160.
Measure RTF before starting it.

---

## 3. Measured facts used by this plan

From `Reports/burst-concurrency-2026-11-15.md` and IDEA-0002:

- Current runtime: 4 on one T4, 5 on two T4s, p95 <= 350 ms. CPU-bound.
- Single stream T4: TTFA p50 47.9 ms, p95 56.3 ms, RTF 0.234.
- Flow-LM step: 12.4 ms at B=1, 12.7 ms at B=32, 15.0 ms at B=64. Nearly flat.
- Prefix prefill, 100 tokens: 16.4 ms at B=1, 152 ms at B=32, 307 ms at B=64.
- Mimi decode, 1 frame: 5.0 ms at B=1, 10.5 ms at B=32, 20.7 ms at B=64.
- At B=32, GPU time is 7.2 ms per step. Attention is 40%, matmul 33%.
- Voice prefix: about 81 frames of the about 100 token prefix.
- First text chunk: about 18 tokens typical, at most 50 by the model's splitter.

CALC TTFA at 100 tokens = prefill + first decode + 10 ms overhead:

| B | TTFA |
|---|---|
| 16 | about 100 ms |
| 32 | about 175 ms |
| 48 | about 250 ms |
| 64 | about 330 ms |

This is why B=64 is the FP32 ceiling at 350 ms. FP16 and a shorter prefix
are needed to go higher.

---

## 4. What already works in the repository

The training code has a batched ragged generator:

- `training/modules/model.py::generate`
- It takes per-row token tensors and voice latents with different lengths.
- It right-aligns each row as `[BOS, voice, text]`, sets `pad`, and runs one
  batched prefill.
- It tracks per-row EOS and per-row end frames.
- `training/tests/test_smoke.py::test_generate_ragged_matches_batch_of_one`
  proves batched rows match batch-of-1 within 2e-3 at temperature 0.

The Mimi decoder state has a batch dimension. `decode_from_latent` accepts
`[B, T, C]`. Batched codec decode needs no new codec.

This removes most correctness risk for ragged static batching.
The missing piece is streaming decode of batched latents.

---

## 5. Why shared voice KV is not first

The idea is good: cache the voice KV once, copy it to every row, prefill only
the text. It cuts prefill by about 60% to 80%. But the current code blocks it:

1. `pocket_tts/modules/attention.py:14` takes only the first row's offset:
   `offset_value = int(offset.view(-1)[0].item())`.
   `complete_kv` also raises when rows have different offsets.
2. `pocket_tts/modules/attention.py:86` `rope_offset` returns
   `state["offset"].view(-1)[0]`. RoPE uses one scalar for the whole batch.
3. `pocket_tts/modules/rope.py:31` does `ts = ts.view(-1, 1, 1)`. A per-row
   tensor offset would flatten to `B*T`, not `[B, T]`. Per-row RoPE needs a
   code change and a parity test.

Rows with different text lengths need different logical positions for their
text tokens. A masked gap is not enough, because RoPE uses relative distance.
So shared voice KV needs per-row positions first.

Decision: use the training right-align path for Phase B. It is correct today.
Keep shared voice KV as a Phase E spike. Start it only if TTFA still binds
after FP16, prefix reduction, and RTF work.

---

## 6. Phase plan and gates

### Phase A: spikes (no product code)

| ID | Question | Output | Decides |
|---|---|---|---|
| S1 | FP16 prefill, step, decode at B=1 to 64. Which SDPA kernel? Does the `float32` cast block it? | Table on T4. Same on L4 if available. | V6, Phase C numbers |
| S2 | Confirm scalar RoPE and equal-offset rule. Prototype per-row positions. How big is the diff? | Yes or no, plus a patch outline | V7, continuous batching |
| S3 | Voice prompt 2, 3, 4, 6.5 s: similarity, WER, UTMOS in 3 languages | Table | V4 |
| S4 | First text chunk 8, 16, 24, 50 tokens: WER, prosody | Table | V5 |
| S5 | Can the step and decode be captured in a CUDA graph at fixed B? What blocks it? | Yes or no, plus blockers | V8 |

Gate A: all five have run reports. Facts enter `.stageset/facts.md` only after
a PASS report.

### Phase B: core static batched server

- V1 batched scheduler, V3 batched state build (no deepcopy), batched decode.
- FP32. One process. T4.
- Harness v2: unique texts, mixed lengths 5 to 50 tokens, 3 bursts per B.
- Gate B:
  - Parity within 2e-3 for B=4, 16, 32, every row, ragged, per-row EOS.
  - Measured N at 350 ms is 32 or more.
  - No error and no OOM.
Phase B measured (see `.stageset/runs/20261115-142500-RUN-batch-harness.md`): B=32 p95 TTFA 327.0 ms with parity diff 1.07e-04; B=30 p95 278.8 ms; B=34-36 fail p95. Safe operating point: B=30.
S1 FP16 spike measured (see `.stageset/runs/20261115-143500-RUN-fp16-spike.md`): FP16 backbone viable; B=64 p95 233.2 ms, 192/192 under 350 ms, RTF 0.008, VRAM 3313 MB. Parity corr 0.998, diff 0.036789. Quality gate pending.
FP16 formalized (see `.stageset/runs/20261115-144500-RUN-fp16-formalize.md`, `.stageset/sessions/coding-fp16-quality-wavs.md`): `Code/batch/fp16.py`, `Code/probes/check_batch_fp16.py` PASS with warning (FP16 B1-vs-B32 corr 0.9469). Manual listening gate PASSED on the regenerated WAVs (`Code/probes/out/fp16_quality/`, FACT-0016). A Mimi decoder state bug caused the first bad gate (FACT-0015). Phase C is unblocked. V4/V5 levers implemented and probed on T4: B=96 p95 under 350 ms for every pair, B=128 unstable. Lever WAVs passed the owner listening gate (FACT-0018). Next: randomized 3-burst probe, choose the default, then B=128 and Phase D RTF work. For L4, rerun FP16/BF16 checks and record facts.

### Phase C: prefill reduction

Order: V6 FP16, V4 shorter voice, V5 capped first chunk, V11 length buckets.

- Gate C1 (V6): FP16 quality gate passes. N is 96 or more.
- Gate C2 (V4, V5): quality gate passes. N is 128 or more, or RTF binds.

### Phase D: RTF side

- V8 CUDA graphs or compile, V9 decoder grouping, V10 finished-row masking.
- Re-profile first. Use the real bottleneck.
- Gate D: aggregate RTF below 1.0 at target N. 30 minute soak, zero errors,
  stable p95.


### Phase D progress (2026-11-15)

- V9 decoder grouping: `decode_group` in `Code/batch/batched_stream.py` (default 1). dg=2 near-identical output but worse TTFA at B=128 (FACT-0030). Kept default 1.
- V10 active-set compaction: `compact` flag (default True). T4 cond profile 5 bursts: B=128 p95 272.7 ms (636/640), B=144 p95 300.5 ms (700/720), B=160 p95 337.7 ms (800/800) (FACT-0031). Major gain.
- V8 manual CUDA graph: **deferred (later if wanted)**. `torch.compile` no gain (baseline 14.05 vs 14.68–15.73 ms/step, B=128, FACT-0032). Dynamic batch/state compaction makes fixed-shape capture hard; benefit uncertain. Not blocking next work.
- Gate D (TTFA stability): **deferred (later if wanted)**. B=160 soak, 475 sequential bursts (160 parallel/burst), 76k req, ~23 min, 0 errors/OOM (FACT-0033, `20261115-215304-RUN`): 74,115/76k <350 ms (97.52%), burst p95 median 275.8 ms, p95-of-p95 416.6 ms, max 562.3 ms, 64/475 bursts p95>350. RTF pass (median 0.0015, p95 0.0025). Stable sustained <350 ms likely ~B=128–144. Moved to next optimizations.
### Phase E: serving and L4

- V11 admission control, V12 two-batch scheme only if staggered traffic matters.
- Repeat Gates B to D on L4. Do not extrapolate from T4.
- V7 shared voice KV only if TTFA still binds.

### Later, with owner permission

- TensorRT or ONNX Runtime. Check the provider in the log. Feather had a silent
  fallback.
- INT8 or FP8 on L4. Only after FP16 passes quality.
- Edge track. Separate idea file.

---

## 7. Lever table

| ID | Lever | Priority | Acts on | Expected effect |
|---|---|---|---|---|
| V1 | Static batched scheduler + batched decode | P0 | Everything | 4 to 32+ |
| V2 | Hot-path cleanup: cache module list, remove logging, reuse buffers | P0 | Step, CPU | 5 to 8 ms per step |
| V3 | Build batch KV with one GPU copy, no per-row deepcopy | P0 | CPU, memory | Removes 0.3 s CPU at B=64 |
| V6 | FP16 | P1 | Prefill, decode | 1.5x to 2.5x prefill, 1.5x decode |
| V4 | Shorter voice prompt, about 3 s | P1 | Prefill | About -43% prefix width |
| V5 | Cap first text chunk at 16 to 24 tokens | P1 | Prefill, p95 | Cuts worst-case width |
| V11 | Text-length buckets, admission control | P1 | p95 | Stops one long text hurting all |
| V8 | CUDA graphs or compile, bucketed by B | P2 | Step, CPU | Removes launch cost |
| V9 | Decoder grouping, 2 to 4 frames per call | P2 | Decode | Raises RTF ceiling |
| V10 | Mask finished rows, compact later | P2 | RTF | Stops waste on short rows |
| V7 | Shared voice KV with per-row positions | P3 | Prefill only | -60% to -80% prefill, high cost |
| V12 | Two-batch scheme for staggered traffic | P3 | TTFA | Protect first chunk |

---

## 8. Harness v2

The old burst test used one sentence for every request. That hides the ragged
cost. The new harness must use unique texts with mixed lengths.

For each B in 1, 8, 16, 32, 48, 64, 96, 128, 160, 192:

- N unique texts, token lengths spread from 5 to 50.
- One shared voice, preloaded.
- All requests start at t0. Full stream consumed.
- Record p50, p95, p99 for first chunk and first non-silent.
- Record the share under 350, 300, 200, and 100 ms.
- Record aggregate RTF and peak VRAM.
- Run 3 bursts per B. Pool the samples.
- No errors and no OOM.

The report must state which B is limited by TTFA and which by RTF.

---

## 9. Quality gates

Owner must approve these limits before Phase C.

- Batched equals single: latents and audio within 2e-3, fixed seed, temp 0.
- WER: no worse than +1.0 point absolute per language.
- UTMOS: no worse than -0.10.
- Voice similarity: no worse than -0.01.
- All 7 languages. Malayalam, Kannada, Telugu are mandatory.
- Same clips for every variant. Raw audio in `Code/probes/out/`.

Keep an FP32 switch for every lever.

---

## 10. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| FP16 quality drop | Bad audio on weak languages | Per-language gate, FP32 fallback |
| FP16 gain is small on T4 | Lower N | S1 first; adjust targets |
| CUDA graph blocked by Python state | No step gain | S5 before V8 |
| Per-row RoPE bug | Wrong audio | S2, parity test |
| Prefill width from long first chunks | p95 tail | V5, V11 |
| Finished rows waste decode | RTF above 1 | V10 |
| 4 vCPU saturation | Tail latency | One process, V2, V8 |
| TensorRT silent fallback | False speedup | Provider check, owner permission |
| L4 not available | Wrong target | Treat L4 as unmeasured until tested |

---

## 11. Permission gates

Ask the owner before:

1. TensorRT or ONNX Runtime work.
2. INT8 or FP8 quantization.
3. Per-row RoPE and shared voice KV (risky attention change).
4. Relaxing any quality gate.
5. Continuous batching for staggered traffic.

---

## 12. Immediate next actions

1. Approve this strategy.
2. Write SSLD-005: Phase B core static batched server, target 32 on T4.
3. Write the harness v2 check first. It is the gate for every later phase.
4. Run S1 FP16 as a parallel spike, because it decides Phase C targets.
5. Do not start V7, V8, or TRT before their gates.

Decision needed from the owner: accept the commit targets (32, 96, 128) and the
quality limits in section 9.

---

## 13. Per-GPU reproduction (T4 now, L4 later)

Every TTFA result is GPU-specific. Do not mix results from different GPUs.
Keep one result file per GPU.

### Environment

1. Run `SSLD-001` to install `pocket-tts` and download the model.
2. Check `nvidia-smi --query-gpu=name --format=csv,noheader`.
3. If the package is not installed, run `pip install -e /kaggle/working/pocket-tts --no-deps`.

### Probe commands

```bash
python Code/probes/bench_batch_server.py --bs 96,128 --max-b 128 --bursts 3 --fp16 --out Code/probes/out/bench_<gpu>.json
python Code/probes/probe_prefill_levers.py
```

The probe JSON has `gpu_name` and `config`. Copy the merged JSON to
`Code/probes/out/probe_prefill_levers_<gpu>.json` before the next GPU run.

### Rules

- Use the same voice file, texts, bursts, and temperature on T4 and L4.
- Use 3 bursts and random order when the run is short.
- A p95 under 350 ms on T4 is not proof for L4. Measure again.
- Record each GPU result as a new fact. Keep the T4 fact as CURRENT.
- Mark a fact SUPERSEDED only when the same GPU and setup changes.

### Measurement note (T4, 2026-11-15)

The lever probe ran each config in a separate process. That biased the ranking.
A clean in-process test at B=96 gave median first-chunk time 163.8 ms at 4.0 s,
145.2 ms at 3.0 s, and 130.0 ms at 2.0 s. Shorter voice is faster, as expected.
FACT-0019 numbers are valid. Its ranking is not. FACT-0020 holds the cause.

Open items before a default is set:

1. Run all lever configs in one process. One model load, alternating rounds.
2. Cut the voice to `voice_seconds` first, then call `end_on_pause`. A cut after
   `end_on_pause` can end the prompt on speech. The codec notes say this is bad.
3. Keep `max_first_tokens=None` as the default. A cap truncates the text. The
   streaming server must generate later chunks to speak the full text.
4. Confirm B=128 with voice 3.0 s in the clean test.
- **Selected (user, 2026-11-15, settled):** T4 **voice 4.0 s, cap 16, B=128** (target, may increase). Unbiased 4v3 probe (FACT-0028, `20261115-205122-RUN`): 4.0/16 B96 p95 264-307 ms 100%<350, B128 p95 372-400 ms 94.4%; 3.0/16 worse. B=128 needs Phase D/correct conditioned-KV reuse for consistent <350; B=96 is safe now.

## 14. Voice profiles

- Goal: save voice conditioning once and reuse forever. Keep normal 4.0 s path when no profile is chosen.
- Usage: `Code/batch/VOICE_PROFILES.md`.
  - Normal: `BatchedStream(model, voice=wav, voice_seconds=4.0, ...)`
  - Create conditioned profile once: `stream.save_voice_profile(path, conditioned=True)` (encoded voice + conditioned KV state)
  - Use profile: `BatchedStream(model, voice_profile=path, ...)` (opt-in, KV-reuse fast path when text lengths uniform)
- Selected operating point (user): T4, 4.0 s, cap 16, **B=128** target. With conditioned profile: B=128 p95 281–331 ms, 128/128 <350 (FACT-0029). Normal path B=128: 372–400 ms 94.4% (FACT-0028).
- Impl: `Code/batch/batched_stream.py` (cb7cb55 KV-reuse path). Different conditioning path than normal (not bit-identical); quality checked by ear. Uniform first-chunk token lengths required for fast path.

### GPU-agnostic optimizations (SSLD-010, partial)

- V11 helper: `Code/batch/scheduler.py` (bucketing/admission). V12 probe: `Code/probes/probe_pipelined_bursts.py` (CPU prep overlap) B=128 10 rounds p95 272.58 ms, 1280/1280 <350 (FACT-0034).
- Stable soak B=128 (partial, interrupted, salvaged): 305 bursts, 39,040 req, 99.91% <350, burst p95 median 226.21 ms, p95-of-p95 302.22 ms, max 364.49 ms, 2 bursts >350, RTF median 0.0018 (FACT-0035). B=144 not run (time). Data in `Code/probes/out/soak_b128.jsonl`/summary.

### TTFA levers E1/E4/E2 and max B (SSLD-013, 2026-11-16)

- Measurement: use the clean separate-process client. The old 50-180 ms tail was measurement bias (FACT-0044).
- E1: batched tokenizer + one embedding call. Prep 65 -> 2.2 ms at B=128 (FACT-0046).
- E4: frame views, no per-row clone. Emit 26 -> 0.28 ms at B=128 (FACT-0047).
- E2: Mimi decode under FP16 autocast, params stay FP32. Steady B=160 79.1 -> 65.4 ms (FACT-0049).
- E3: decode_group 2/4 is slower. Dropped (FACT-0050).
- Max B on one T4: warm p50 TTFA 67.6/78.8/91.6/107.1 ms at B=128/160/192/224. B=256 OOM (FACT-0048).
- Clean soak with autocast Mimi: B=144 p95 84.1 ms, 100% <350; B=160 p95 95.0 ms, 100% <350 (FACT-0051).
- Next: M2 (Mimi on a second CUDA stream), then M1 (workers per GPU). SSLD-014.
- M2 (second CUDA stream for decode) gives no gain: 69.99 vs 70.68 ms at B=192. The T4 SMs are shared. Dropped (FACT-0052).
- decode_group 2/4 is also dropped (FACT-0050).
- E2 listening gate passed on `/kaggle/working/mimi_compare.wav` (FACT-0053). FP16 decode is cleared for production.

### Cold start and production cap (SSLD-015, 2026-11-16)

- Boot 5.56 s. Prewarm at B=160 costs 636 ms and brings cold p95 from 613 to 148 ms (FACT-0055).
- Prewarm is on by default: `ARSENAL_PREWARM=1`, `ARSENAL_PREWARM_B=192`, `ARSENAL_PREWARM_FRAMES=1`. Set `ARSENAL_PREWARM=0` to disable.
- Production cap: B=192 (cold p95 203 ms, RTF 0.82). B=160 is the safe fallback (FACT-0056).
- Prefetch and CUDA_CACHE_PATH give no gain (FACT-0057, FACT-0058).
- Later phase, Modal only: memory snapshot (`snap=True`) should run import, weight load and prewarm once per image version, so the per-boot cost goes to zero. Do not build it now.

### SSLD-016 results (2026-11-16)

- FP16 weight cache: corr 0.9999991, encoder stays FP32. Steady B192 57.2 ms, B224 ~66 ms (FACT-0060, FACT-0063).
- Component split: flow ~13.5 ms, Mimi ~27 ms, other ~5 ms. Mimi is the target.
- B=224 passes: p95 112 ms, max 119 ms, RTF 0.824, peak 7.08 GB. Cap candidate B=224 (FACT-0064).
- B=256 fits now (3.24 GB allocated). Memory is no longer the blocker; steady RTF is (FACT-0065).
- Voice-embedding cache: 650 ms -> 1.4 ms at boot, audio identical. Prebuild at image time (FACT-0066).
- Shared voice-prefix KV is dropped: voice state is 1.2 MB (FACT-0065).

### Gap and scaling (2026-11-16)

- The 12–18 ms steady gap is EOS/compaction/Python overhead (~8–10 ms profiled). Not harness IPC (server-side timings).
- B=224 is the confirmed cap: p95 112 ms, max 119 ms, RTF 0.824. B=256 gives RTF 0.902 (>0.85), rejected.
- Two processes per T4 are not viable (VRAM). The only remaining compute lever is Mimi (26–29 ms).

### Step 1–4 results (2026-11-16)

- GPU busy ~60% at B=224; CUDA graphs skipped (not under 70%).
- Other 8–10 ms from EOS/compaction/Python; threshold patch no gain.
- Two processes per T4 run but share GPU (latency worse than one B=224).
- Cap remains B=224 (B=256 RTF 0.902).

### Step 1–4 (2026-11-16, this turn)

- other 8–10 ms unchanged (threshold patch); <3 ms not met (parity OK).
- Mimi CUDA graphs: attempted, state blocker; no replay savings measured, skipped.
- Frame growth by index not measured (OOM at long frames).
- Voice cache prebuild script added; expected boot saving ~0.65 s.
- Final single-T4 cap: B=224 (p95 112, max 119, RTF 0.824). B=256 rejected RTF 0.902.

### Memory safety (step 1)

- B=224 OOM at max_frames=300: Mimi KV sized to (max_frames+4)*16, no window. No fragmentation fix.
- Safe cap: max_frames <= 192 (15.36 s) at B=224 to keep >=1.5 GiB free.
- Need admission guard + text chunking by frame limit.

## Final single-T4 summary (closed)

- Cap: B=224, conditioned profile, FP16 Mimi weights, prewarm B=192 frames=1. p95 112.2 ms, max 118.6 ms, RTF 0.824.
- Safe limit: max_frames <= 192 (15.36 s) at B=224 (>=1.5 GiB free). Guard raises ValueError if exceeded.
- What worked: E1 prep batching, E4 emit copy removal, Mimi FP16 weights (decoder-only), voice cache (650→1.4 ms), prewarm accepted.
- What failed (see FACT-0085): M2, decode_group, prewarm budget rule, full Mimi cast, CUDA graphs (blocked), EOS threshold gain, long-frame profiling OOM, two-process scaling, B256 RTF, prefetch/cache boot gains.
- Open: long-text chunker, Modal build (SSLD-017), L4 re-run, wire voice cache build.
