---
id: IDEA-0002
title: High-concurrency burst plan for pocket-tts on one T4 or L4
status: DISCOVERY
priority: P0
created_in: .stageset/sessions/ideation-pocket-tts-multilingual.md
updated_in: .stageset/sessions/ideation-batch-server.md
created_at: 2026-11-15T00:00:00+05:30
updated_at: 2026-11-15T14:07:25+05:30
related_ideas: [IDEA-0001]
related_reports: [Reports/burst-concurrency-2026-11-15.md]
---

# High-concurrency burst plan for pocket-tts on one T4 or L4

Scope: one GPU. Unique text per request. Same cloned voice. Streaming on.
Metric: largest N where p95 time to first non-silent audio (TTFA) is at most 350 ms.
Sustained streaming must also keep RTF below 1.0.

Status: design draft for review. Not an SSLD yet.
Do not treat the estimates below as measured end-to-end results.

---

## 1. Short answer

| Setup | First implementation (FP32 static batch) | Target (FP16 + compile + shared voice) | Practical sustained limit |
|---|---|---|---|
| 1x T4 | **32 to 48** | **64 to 96**, stretch 128 | about 128 to 160 |
| 1x L4 | **64** | **128**, stretch 192 to 256 | about 256 to 320 |

Recommended SSLD target: **48 on T4, 96 on L4** at p95 TTFA <= 350 ms.
Then raise the target after the first batched prototype passes quality checks.

The current runtime gives **4 on one T4** and **5 on two T4s**. It is CPU-bound.
The main gain comes from one batched scheduler, not from more GPUs.

Confidence: medium. The flow-LM and decoder numbers below are measured on a T4.
The end-to-end TTFA is calculated from them. A prototype must confirm it.

---

## 2. Measured baseline

Source: `Reports/burst-concurrency-2026-11-15.md`.

| Setup | Max N, p95 <= 350 ms | Share under 350 ms |
|---|---|---|
| 1x T4 | 4 | 32/32 = 100% |
| 2x T4 | 5 | 15/15 = 100% |

- N=6 on one T4: p95 511 ms, 78% under 350 ms.
- N=6 on two T4s: p95 463 ms, 89% under 350 ms.
- The second GPU adds one request. The host has 4 vCPU and the runtime uses two
  Python threads per request. The tail is CPU scheduling delay, not GPU compute.
- One model instance shared by threads is worse. N=4 gave p50 428 ms and 6.9 s wall
  for 4 streams. Do not use threads on one model instance.

Single-stream T4 baseline: TTFA p50 47.9 ms, p95 56.3 ms, RTF p50 0.234.
Peak VRAM 496 MB. Load 0.99 s.

---

## 3. Where the time goes

Microbenchmark on one T4, FP32, batch dimension B, a 100-token prefix,
and 30 steady-state steps. Time is per step, in ms.

| B | Prefix prefill 100 | Flow-LM step | Mimi decode, 1 frame |
|---|---|---|---|
| 1 | 16.4 | 12.4 | 5.0 |
| 4 | 28.6 | 14.1 | 5.1 |
| 8 | 45.3 | 14.3 | 5.1 |
| 16 | 86.1 | 13.7 | 6.5 |
| 32 | 152.4 | 12.7 | 10.5 |
| 64 | 306.7 | 15.0 | 20.7 |

Key facts:

- The flow-LM step is almost flat from B=1 to B=32. It is launch and CPU bound,
  not GPU bound, at small batches.
- The prefix prefill grows linearly with B. At B=64 it is 307 ms for 100 tokens.
  This is the main TTFA cost at high N.
- The decoder grows with B but stays below the 80 ms frame period up to B=64.
- At B=32, a profile shows 7.2 ms GPU per step. Attention is 40% of GPU time,
  matmul 33%. The profiler reports 18.6 ms CPU per step, but the profiler adds
  overhead. `increment_steps` alone is 0.26 ms. A large part of the step is
  Python and small-kernel overhead.

Calculated TTFA for a 100-token prefix = prefill + first decode + about 10 ms overhead:

| B | TTFA estimate |
|---|---|
| 16 | about 100 ms |
| 32 | about 175 ms |
| 48 | about 250 ms |
| 64 | about 330 ms |

For a worst-case first chunk of 50 text tokens (prefix about 132 tokens),
multiply the prefill by 1.32. Then B=48 is about 300 ms and B=64 is about 430 ms.

---

## 4. Gaps in the current runtime

1. **No batched generation API.** `generate_audio_stream` is batch 1.
   `init_states` is called with `batch_size=1` in every inference path.
2. **One process or one model instance per request.** This repeats model load,
   voice prefill, and Python work. It is the cause of the 4-request limit.
3. **Equal offsets are required.** `complete_kv` raises an error when rows in a
   batch have different KV offsets. A batch must run in lockstep.
4. **Voice state is deep-copied per request.** 3.84 MB and about 5 ms each.
   At B=64 this is 246 MB and 0.3 s of CPU work.
5. **The whole voice prefix is recomputed per request.** The voice is about 81
   frames. It is most of the 100-token prefill. The same voice is identical
   for every row.
6. **Per-step Python overhead.** `increment_steps` walks `named_modules()` every
   step. Logging and `display_execution_time` run in the hot path. Many small
   elementwise kernels are launched per step.
7. **The decoder is per-request.** One decoder thread per stream adds CPU
   contention. The decoder itself already supports batch in its state.
8. **No FP16 path.** `flow_lm.forward` casts the transformer output to float32
   before `out_eos` and the flow head. A naive `model.half()` fails. FP16 needs
   a small code change and a quality check.
9. **No finished-row handling in a batch.** A row that hits EOS keeps using
   batch compute until the longest row finishes.
10. **No admission control.** There is no queue and no RTF guard.

---

## 5. Assets already in the repository

The training code already has a batched ragged generator:

- `training/modules/model.py::generate`
- It accepts a list of token tensors and a list of voice latents with different lengths.
- It right-aligns each row as `[BOS, voice, text]`, sets the per-row `pad` field,
  and runs one batched prefill.
- It tracks per-row EOS and per-row end frames.
- `training/tests/test_smoke.py::test_generate_ragged_matches_batch_of_one`
  proves that batched rows match the batch-of-1 path within 2e-3 at temp 0.
- `set_state_padding` and the `pad` field in `StreamingMultiheadAttention`
  already drop leading padding from attention.

This removes most of the correctness risk for ragged batching.
The missing part is streaming decode of batched latents.

The Mimi decoder state also has a batch dimension. `decode_from_latent` accepts
`[B, T, C]`. Batched codec decode is possible without a new codec.

---

## 6. Proposed design: batched burst server

One process. One model copy. One GPU. One scheduler.

### 6.1 Request intake

- Accept requests into a queue.
- Open a short collection window, 10 to 20 ms, or close early when the batch is full.
- Take up to B requests from the queue. B is a bucket size: 4, 8, 16, 32, 64, 128.
- Tokenize texts in parallel before the batch starts. Cache the voice state.
- This window is part of the 350 ms budget. Keep it small.

### 6.2 Batch build

- Encode the voice once per unique voice. Project it once.
- For each request, build `[BOS, voice, first_text_chunk]`.
- The first text chunk is at most 50 tokens. The model already splits long text
  into chunks of 50. TTFA depends on the first chunk only.
- Right-align all rows to the widest prefix. Set `pad` per row.
- Allocate one static KV cache `[2, B, prefix + max_frames, heads, dim]`.
- Do not deep-copy a voice state per row. Fill the batch cache directly.

### 6.3 Batched prefill and first frame

- Run one forward over the padded prefix plus the first latent token.
  This is the training `generate` first-step pattern. It avoids a separate
  prefill forward and a wasted sample.
- Use the output to sample the first latent for every row.
- Decode the first latent frame for the whole batch in one Mimi call.
- Emit the first audio chunk to every row. Record TTFA.

### 6.4 Lockstep generation and streaming

- Run the flow-LM step for the whole batch.
- Queue all rows' latents into one batch decoder.
- The decoder runs `decode_from_latent` for the whole batch and returns one
  audio frame per row, 1920 samples per frame (80 ms).
- Push each row's chunk to its own output stream.
- Track EOS per row. Stop appending frames for finished rows.
- The batch ends when all rows are done, or at a max frame count.
- Decode 2 to 4 frames per call when the queue has them. This raises GPU use
  and reduces launch overhead. Tune the value.

### 6.5 Batch completion

- Do not add new requests to a running lockstep batch in the first version.
  The equal-offset rule makes it complex.
- New requests wait for the next batch. With short audio, this is acceptable.
- Optional later: slot-based continuous batching. See section 8.

---

## 7. Optimization levers, in order

### L1. Batched static burst scheduler (core)

What: one process, one model, batched prefill, batched flow steps, batched decode.

Expected effect: this is the difference between 4 and 32 to 64 on T4.
Without it, no other lever matters.

Cost: medium. Most logic exists in the training generator. Streaming decode is new.

Risk: audio must match the batch-of-1 path. The training test gives a pattern.
Use temp 0 and compare latents and audio for a fixed seed.

### L2. Remove hot-path Python overhead

What:

- Cache the list of stateful modules and update offsets directly.
- Remove logging and `display_execution_time` from the step and decode loops.
- Preallocate input tensors and reuse them.
- Avoid `cat` with empty tensors when the prefix is already built.
- Keep the sampler noise generation on the GPU.

Expected effect: the step is 12.7 ms at B=32 but only 7.2 ms of GPU work.
Removing 5 to 8 ms of CPU and launch overhead helps sustained RTF and lets
bigger batches fit the frame period.

Cost: low to medium. Risk: low.

### L3. torch.compile and CUDA graphs

What: compile the flow-LM step and the decoder for fixed bucket shapes.
Use `mode="reduce-overhead"` or manual CUDA graphs.
Bucket by B and by cache length. Reuse static input and output buffers.

Expected effect: cut per-step launch overhead. Useful for B=64 and above.
The step is already flat to B=32, so most of the TTFA gain is at high N.

Cost: medium. Risk: recompiles on shape changes; keep shapes static.

### L4. FP16 on T4, BF16 or FP16 on L4

What: run the transformer, flow head, and decoder in half precision.
Keep the codec quantizer and any sensitive norms in FP32 if needed.

Gap: `flow_lm.forward` hard-casts to float32. Patch it to keep the compute dtype,
or keep `out_eos` in float32 and cast only its input.

Expected effect:

- Prefill and decoder are matrix and convolution heavy. Expect 1.5 to 2x on T4.
- The step is overhead bound at small B, so the gain is smaller there.
- FP16 attention can use a faster kernel on T4. FP32 uses the mem-efficient
  cutlass path, which is 40% of step GPU time.

Cost: medium. Risk: quality. Test all 7 languages, especially Malayalam,
Kannada, and Telugu. Compare WER, UTMOS, and voice similarity.

### L5. Shared voice-prefix KV

What: prefill the voice prefix once per voice, then reuse its KV for every row.
Only the text part is prefilled per request.

Why: the voice is about 81 of 100 prefix tokens. Removing it cuts prefill by
about 60%. At B=64, prefill drops from about 307 ms to about 120 ms.
That moves B=64 from marginal to comfortable and opens B=96 to 128.

Gap: text lengths differ. The current `pad` mask only handles leading padding.
Options:

1. Prefill voice once, then prefill text for each row separately and merge the
   KV. Text is short, but B separate forwards cost CPU.
2. Add a segment-aware attention mask: keep the shared voice positions for all
   rows, mask only the padded text positions. This is the clean solution.
3. Group requests by text length and use the existing right-align path. Simpler,
   less effective.

Cost: medium to high. Risk: medium. Validate attention masks carefully.

### L6. Decoder batching and frame grouping

What: decode all rows in one call; decode 2 to 4 frames per call.
Use one decoder worker for the batch, not one per request.
Pipeline flow-LM generation and decode on two CUDA streams.

Expected effect: sustained RTF stays below 1 at high B. The decoder is 10.5 ms
at B=32 and 20.7 ms at B=64 for one frame. Two-frame grouping reduces the
number of calls and raises GPU use.

Cost: medium. Risk: first-chunk latency must not grow. Decode the first frame
alone, then group later frames.

### L7. Finished-row handling

What: stop sampling and decoding finished rows. Compact the batch at a frame
boundary, or mask them and skip their compute.

Why: with unique texts, EOS times differ. A batch runs until the longest row.
Without compaction, short rows waste compute and memory bandwidth.

Gap: `complete_kv` needs equal offsets. Compaction of rows that are all at the
same offset is safe. Adding a new row at a different offset is not. For the first
version, mask finished rows and keep the batch. Compaction of finished rows is a
later optimization.

Cost: low for masking, medium for compaction.

### L8. CPU-side pipeline

What:

- Tokenize in a small thread pool or a native tokenizer. The repo has a `rust/` tree.
- Cache voice embeddings and voice KV.
- Pin the scheduler and decoder threads. Avoid oversubscription.
- Use a single process. Do not use one process per request.

Expected effect: the host has 4 vCPU. The batched scheduler removes most
per-request Python work, but tokenization and request handling still use CPU.
Keep the CPU path off the first-audio critical path.

### L9. Admission control

What: estimate the batch RTF before admitting a request. Queue or reject when
the next batch would break the 350 ms target or sustained RTF.

Why: protects p95. A few long requests can raise the prefill width for the
whole batch. Bucket by text length to reduce this.

### L10. Kernel and backend work (later)

- Fused norm, fused MLP, fused sampler.
- FlashAttention in FP16 where available.
- TensorRT or ONNX Runtime for the backbone, with a check that it did not fall
  back silently. Feather had this failure.
- INT8 or FP8 linear layers on L4, only after FP16 quality passes.

These are second-order after batching, FP16, and compile.

---

## 8. Continuous batching, if needed later

The first version uses static bursts. All rows start together and run in lockstep.
This matches the burst metric.

For staggered arrivals, continuous batching is possible but harder:

- `complete_kv` requires the same offset for every row.
- A new row must join with a KV cache filled up to the current offset, or be
  prefilled separately and merged.
- Option A: pad the new row's cache with masked positions up to the current
  offset, then write its prefix at the end. The prefix is "spoken" at join time.
- Option B: run a separate small prefill batch, then copy its KV into free slots
  of the main cache. Requires cache slot management.
- Option C: keep two batches, a "first-chunk" batch and a "sustained" batch.
  New users enter the first-chunk batch with priority, then move to the
  sustained batch. This protects TTFA without complex cache merging.

Start with C if staggered traffic matters. It is simpler than A or B.

---

## 9. Expected concurrency and confidence

Assumptions:

- Same voice for all requests, or a small set of cached voices.
- First text chunk at most 50 tokens.
- One process, one model, one GPU.
- p95 TTFA <= 350 ms, server-side time, first non-silent chunk.
- Sustained RTF <= 1.0 for the full stream.
- 4 vCPU host, similar to the measured machine.

| Configuration | T4 | L4 | Confidence |
|---|---|---|---|
| Current runtime | 4 | not measured | high for T4 |
| Static batch, FP32, no compile | 32 to 48 | 64 | medium-high |
| + hot-path cleanup + compile | 48 to 64 | 96 | medium |
| + FP16/BF16 | 64 to 96 | 128 | medium |
| + shared voice KV | 96 to 128 | 192 to 256 | medium-low |
| Sustained limit | about 128 to 160 | about 256 to 320 | low-medium |

Recommended plan:

1. Build the static batched prototype in FP32. Target 32 on T4. Measure.
2. Add hot-path cleanup and compile. Target 48.
3. Add FP16. Target 64.
4. Add shared voice KV and admission control. Target 96.
5. Repeat on L4. Target 128 to 192.

Do not promise 200 to 300 on one T4 for this model without new evidence.
The earlier estimate in IDEA-0001 was based on calculation, not measurement.
The measured prefill cost at B=64 is already 307 ms for 100 tokens in FP32.

---

## 10. Validation plan for the SSLD

Checks, in order:

1. **Batched equals single.** Fixed seed, temp 0. Compare latents and audio for
   B=4, 16, 32 against B=1. Use the training test tolerance. Check every row.
2. **Ragged prefixes.** Unique text lengths. Right-align padding must not change
   any row. Include texts longer than one 50-token chunk.
3. **Per-row EOS.** Short and long texts in one batch. Each row must stop at its
   own end. No extra audio after EOS.
4. **TTFA burst.** B = 1, 8, 16, 32, 48, 64, 96, 128. Three bursts per B.
   Report p50, p95, p99 first chunk and first non-silent. Find max B under 350 ms.
5. **Sustained RTF.** 10-second texts at max B. Aggregate RTF below 1.0.
   No underrun and no growing queue.
6. **Memory.** Peak VRAM below 15 GB on T4 and 24 GB on L4, with 20% headroom.
7. **Quality.** WER, UTMOS, and voice similarity against the FP32 baseline for
   all 7 languages. English first, then Malayalam, Kannada, Telugu.
8. **Soak.** 30 minutes at target B. Zero errors, zero OOM, stable latency.
9. **L4 parity.** Run the same checks on L4. Do not extrapolate from T4.

Raw data goes to `Code/probes/out/`. Results go to `.stageset/results.json`.
The report goes to `Reports/`.

---

## 11. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Batched audio differs from single | Quality regression | Fixed-seed parity test, then listening and WER |
| FP16 quality drop on low-resource languages | Bad output | Per-language WER/UTMOS gate; keep FP32 fallback |
| CPU overhead at B=64 | TTFA tail | Hot-path cleanup, compile, one process, 4 threads |
| Prefill width from long first chunks | TTFA over budget | Bucket by text length, cap first chunk, admission control |
| Finished rows waste compute | Sustained RTF | Mask finished rows, compact later |
| Attention mask bug with ragged text | Wrong audio | Reuse the training `pad` path; add mask unit tests |
| L4 not available for tests | Wrong estimate | Treat L4 numbers as estimates until measured |
| Network and queue time | Budget overrun | Reserve 50 to 100 ms of the 350 ms for the server edge |

---

## 12. Open questions

1. Is the voice the same for all requests, or can it differ? Shared voice KV
   only helps in the first case.
2. Is 350 ms a p95 target or must every user be under it? The plan uses p95.
3. What is the allowed quality drop for FP16? Needed before L4.
4. Is the first chunk one frame (80 ms of audio) or can it be smaller?
5. Is two-GPU support still needed, or is the target single GPU only?
6. Is the deployment CPU 4 vCPU, or can it be 8 or 16? This changes the
   scheduler headroom.
7. Do we need continuous batching for staggered arrivals, or is burst enough?

---

## 13. Decision needed

If this design is accepted, the SSLD should start with:

- SSLD-005: batched static burst scheduler, FP32, T4, target 32.
- Then a separate SSLD for FP16 and compile.
- Then a separate SSLD for shared voice KV.

Each SSLD must produce a measured burst table and a quality parity report.
