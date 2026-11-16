---
id: IDEA-0004
title: TTFA and burst capacity gain plan (ranked by gain per effort)
status: DISCOVERY
priority: P0
created_at: 2026-11-16T07:30:00+05:30
updated_at: 2026-11-16T07:30:00+05:30
created_in: .stageset/sessions/ideation-ttfa-burst-gain.md
updated_in: .stageset/sessions/ideation-ttfa-burst-gain.md
related_ideas: [IDEA-0003]
related_skeletons: [Skeletons/Code/batch/batched_stream.py, Skeletons/Probes/probe_ttfa_stages.md]
---

# TTFA and burst capacity gain plan

Source: FACT-0033, FACT-0034, FACT-0035, FACT-0041, SSLD-010, IDEA-0003.

## 1. Goal

- Raise B above 128 on one T4. Keep p95 TTFA at most 350 ms.
- First make B=128 p95 TTFA well below 350 ms. Then move to B=160 and above.
- Do easy wins first. Do structural work later.
- Do not start a lever with large effort and small gain.

## 2. Evidence (measured, T4 FP16, cond profile 4.0 s, cap 16, compact)

| Item (ms) | B=32 | B=128 |
|---|---|---|
| text prep (CPU) | 16.7 | 64.0 |
| state clone/init | 2.9 | 8.3 |
| cond text into state | 54.8 | 34.0 |
| flow step0 | 17.0 | 19.5 |
| mimi decode0 | 55.0 | 47.4 |
| TTFA compute subtotal | 146.5 | 173.4 |
| steady flow per frame | 16.5 | 18.9 |
| steady mimi per frame | 17.3 | 38.3 |
| steady total per frame | 33.8 | 57.2 |

Facts from this table:

- At B=128, TTFA compute is 173 ms. Measured p95 is 225 to 350 ms.
  About 50 to 180 ms is not model compute. Nobody measured it yet.
- Steady cost is 57.2 ms for each 80 ms frame at B=128. Headroom is small.
  This is why B=160 is unstable.
- Flow time is flat when B grows 4x (16.5 to 18.9 ms). This suggests flow is
  limited by CPU launch overhead, not GPU compute. HYPOTHESIS. Test in E0.
- Mimi time grows with B but less than 4x (17.3 to 38.3 ms). A fixed cost per
  call exists. Grouped decode can reduce it. HYPOTHESIS.
- Text prep is 64 ms of pure CPU on the critical path. Move it off the path.
- The profile is noisy. Cond text is slower at B=32 than at B=128. Mimi decode0
  at B=32 is 3x its steady cost. Re-measure with warmup, CUDA events, N >= 50.

## 3. Rules for every lever

- Run the parity check and the listening gate for any lever that changes audio.
- Record a FACT with before and after numbers (p50, p95, B, GPU).
- Stop rule: drop a lever if it gains less than 15 ms p95 TTFA or less than 5% B.
- Time box: one lever, one session. If it fails, record the failure and move on.
- Do not retry INT8, INT4, ONNX or TensorRT. All failed on T4.

## 4. Ranked levers

### Tier 0. Measure first

**E0. Stage timestamps and a separate load generator.**
- Add per-request timestamps: arrive, admitted, prefill done, flow0 done,
  mimi0 done, emitted.
- Run the load generator in a separate process. A client in the same process
  takes CPU and adds bias to TTFA.
- Report p50 and p95 for each stage at B=128 and B=160.
- While a step runs, log GPU utilisation and CPU utilisation.
- Output: a table that explains the 50 to 180 ms gap.

### Tier 1. Easy wins

**E1. Tokenize and embed text at request arrival, in batch.**
- Use a batch tokenizer call and a thread pool. Cache by text.
- Expected gain: about 55 ms TTFA at B=128.

**E2. Check the Mimi decoder dtype. Move it to FP16 if it is FP32.**
- Only the backbone is confirmed FP16. Mimi may still run in FP32.
- Gate: listening check. Expected gain: large if FP32. Zero if already FP16.

**E3. Sweep `decode_group` (V9) for steady frames. Keep 1 for the first chunk.**
- Decode 2 or 4 frames per Mimi call after the first chunk.
- Expected gain: Mimi steady 38 ms down to about 20 to 28 ms.

**E4. One batched D2H copy per step. Async EOS flags.**
- Copy all chunk audio in one pinned tensor with an event. Slice views per request.
- Read EOS flags one frame late. Remove `.item()`, `.cpu()`, `synchronize()`
  from the step. Expected gain: 10 to 40 ms from the tail.

**E5. Adaptive admission window.**
- Zero wait when idle. Close the batch at a step boundary or after 2 to 3 ms.

**E6. Slot pool with in-place state reset.**
- Replace state clone/init by reset of a preallocated slot.
- Expected gain: about 7 ms TTFA at B=128.

**E7. Jitter removal.**
- `gc.disable()` and `gc.freeze()` after warmup.
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
- Pre-warm every bucket shape. Pin CPU cores for the worker.

### Tier 2. Bigger multipliers

**M1. Several worker processes per GPU, and one set per GPU.**
- Run N persistent workers per T4 (test N = 1, 2, 3). Each owns B/N slots.
- Add a router with least-loaded routing. Pin 1 core per worker (4 vCPU total).
- Then use both T4 cards. Expected: up to 2x B from the second card alone.

**M2. Overlap Mimi decode with the next flow step on a second CUDA stream.**
- Frame t+1 needs only the latent of frame t. It does not need the audio of t.
- Steady time can go from flow + mimi (57 ms) toward max(flow, mimi) (40 ms).
- Gate: parity check.

### Tier 3. Structural

**S1. Cohort pipelining and first-clause prefill.**
**S2. Shared-prefix attention for voice KV.**
**S3. Continuous admission.**

### Tier 4. Parked

- CUDA graphs (V8). Gain too small for the effort. Retry only if E0 shows
  large GPU idle gaps after Tier 1 and Tier 2.
- INT8, INT4, ONNX, TensorRT on T4. All failed. Do not retry.

## 5. Expected result (estimates, not measured)

- After E0 to E7: p95 TTFA at B=128 should drop clearly. Target at most 200 ms.
  B=144 and B=160 soaks should become stable. Re-run SSLD-010 T005.
- After E2, E3 and M2: steady cost per frame may drop from 57 ms to 30 to 40 ms.
- After M1: capacity may reach about 2x per box with two T4 cards.

## 6. Living docs

- SSLD-012: E0. Acceptance: a stage table and new p95 at B=128 and B=160.
- SSLD-013: E1, E2, E6, E5. Based on the E0 result.
- Later: E3, E4, E7, then M2 and M1.

## 7. Open questions

- Is the Mimi decoder FP32 or FP16 now? (E2)
- Is flow limited by CPU launch overhead? (E0)
- What fills the 50 to 180 ms gap between compute and p95? (E0)
- Does decode grouping create gaps in the audio at the chunk edges? (E3)

## Acceptance criteria

- A run report shows stage p50 and p95 at B=128 and B=160.
- The report states where the 50 to 180 ms gap is.
- The next lever is chosen from measured data.

## Related files

- `Ideas/optimization-strategy.md`
- `Skeletons/Code/batch/batched_stream.py`
- `Skeletons/Probes/probe_ttfa_stages.md`
- `.stageset/facts.md` (FACT-0041)
