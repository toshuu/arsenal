# Modal deployment plan (single-T4)

## Scope
- One NVIDIA T4 per container. One model copy, one stream worker.
- Cap B=224 (conditioned profile, FP16 Mimi weights). B=256 rejected (RTF 0.902).

## Image build
- Copy `Code/model` (`model.safetensors`, `tokenizer.model`, `config.yaml`).
- Build `Code/model/fp16_weights.pt` via `save_fp16_weights` (decoder only) after model load.
- Prebuild voice cache: run `Code/batch/build_voice_cache.py`; set `ARSENAL_VOICE_CACHE` to that dir.
- Set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
- Do not keep a second FP32 decode-weight copy in memory paths beyond load/save.

## Boot order (measured baseline)
1. Import torch/CUDA init.
2. Load model, move to GPU.
3. Enable FP16 backbone (`mimi_fp16=True`), load `fp16_weights.pt`.
4. Prewarm: one stream call, B=160, `max_frames=1`, conditioned profile.
5. Readiness after step 4 + GPU sync.

Measured: ~6.7 s with prewarm in this environment (stream/voice cache matters).

## Concurrency
- Hard cap B=224. Autoscale target 192–200.
- Reject requests with `max_frames` or text exceeding limits before allocation (`BatchedStream` raises `ValueError` when over `ARSENAL_MAX_FRAMES`).
- No two-worker-per-T4 throughput design (worse latency measured).

## Memory snapshot test plan
- A: CPU snapshot after warm load + prewarm; compare restore boot and first TTFA.
- B: GPU snapshot only if A fails (experimental). Keep A default.
- Record snapshot size, restore time, cold TTFA, CUDA/state errors.

## Limits
- B=224: peak alloc grows ~61 MB per `max_frames`. Safe `max_frames <= 192` (15.36 s) to keep >=1.5 GiB free.
- Enforce `ARSENAL_MAX_FRAMES=192` at B=224; never allow init-time OOM from oversized KV.

## Timeouts
- Request timeout >= 2.0 s initially (p95 112 ms at B=224). Tune after live data.
- Set idle timeout from observed burst gaps.

## Measure on Modal cold starts
- Boot to readiness, cold first-request TTFA, steady p95 at B=192/224.
- Peak alloc/reserved at cap, rejected-over-limit count.

## L4 re-run plan
- Soaks: conditioned profile, FP16 weights, mixed lengths, 20 bursts at B=224/256/288.
- Record p50/p95/max TTFA, RTF, peak VRAM, OOM/errors. Update this doc before rollout.
