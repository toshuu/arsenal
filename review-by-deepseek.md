# Review by DeepSeek: Pocket TTS on T4 and L4

Date: 2026-11-14
Reviewer: DeepSeek
Scope: `Thanushttk/pocket-tts-multilingual` and the `kyutai-labs/pocket-tts` runtime.
Code inspected at `kyutai-labs/pocket-tts` commit `9e8413e` (2026-11-13).
Target: lowest latency and highest concurrent streams on Tesla T4 and NVIDIA L4.
Arsenal context: this review covers the model in `Ideas/pocket-tts-multilingual-optimization.md` and `LivingDocs/SSLD-001-pocket-tts-phase-0.md`. Arsenal has no serving code yet. The review targets the upstream runtime that Phase 1 must replace.

## 1. Verdict

Yes, this project can be optimized heavily.

The model is small: 109.5M parameters, 438 MB in FP32. The current runtime is a CPU-first, single-stream reference. It is not a GPU serving engine. The main blockers are:

1. Seven or more host syncs per generated frame.
2. One Python thread pair per request.
3. No batching.
4. A full copy of the voice KV cache for each request.
5. A decoder KV cache sized for the whole generation, not the 250-frame context.
6. A new attention mask and new RoPE tables on every layer and every frame.

The largest single win is to remove the host syncs and make the decode step graph-safe. The largest structural win is continuous batching with a shared voice prefix. With both, 50 to 200 concurrent streams per T4 or L4 and a first-audio latency of 100 to 300 ms are realistic.

The current measured GPU speed is about 6.3x real-time for one stream on a T4 (from the upstream `AGENTS.md`). That is far below what the hardware can do. The model is not compute-bound at batch 1. It is bound by launch overhead, syncs, and Python.

## 2. What the model does

| Item | Value |
| --- | --- |
| Flow LM backbone | 6 layers, d_model 1024, 16 heads, FFN 4096 |
| Flow head | `SimpleMLPAdaLN`, depth 6, dim 512, 1 LSD step |
| Text | SentencePiece, 4000 pieces, 7 languages |
| Audio codec | Mimi-style, 24 kHz, 12.5 frames/s, 80 ms per latent |
| Codec decoder | 2-layer transformer, d_model 512, context 250, plus SEANet |
| Total parameters | 109.5M |
| Generative parameters | about 99.7M (flow LM + decoder) |
| Weight size | 438 MB FP32, 219 MB FP16 |
| Default precision | FP32 |
| Decode steps | 1 |
| Temperature | 0.3 |
| Voice prompt | Mimi encoder, cached per voice |

The generation loop is:

1. Encode the voice prompt once. Store the flow-LM KV state.
2. Prefill the text tokens into a copy of that state.
3. For each 80 ms frame, run the 6-layer transformer, the flow head, and the EOS head.
4. Send the latent to a decoder thread.
5. The decoder runs the 2-layer transformer, the SEANet decoder, and yields PCM.
6. Check EOS on the host and stop.

The model is autoregressive at 12.5 steps per second. The per-frame compute is small. The sequential dependency is the hard part.

## 3. Measured facts from the code and weights

### 3.1 Parameter groups

| Group | Parameters |
| --- | ---: |
| `flow_lm.transformer` | 75.52M |
| `flow_lm.flow_net` | 9.76M |
| `flow_lm.conditioner` | 4.10M |
| `mimi.decoder_transformer` | 6.30M |
| `mimi.decoder` | 3.97M |
| `mimi.encoder_transformer` | 6.30M |
| `mimi.encoder` | 2.93M |
| Other | about 0.6M |

The flow transformer is 12.59M parameters per layer. The decoder transformer is 3.15M per layer.

### 3.2 KV cache size per stream

Flow LM, per frame, per layer:

```
2 (K and V) * 16 heads * 64 dim * 4 bytes = 8,192 bytes
```

Six layers:

```
8,192 * 6 = 49,152 bytes per frame, about 48 KiB
```

For a typical chunk:

| Part | Frames | FP32 | FP16 |
| --- | ---: | ---: | ---: |
| Text prompt | 50 | 2.3 MiB | 1.2 MiB |
| Generated audio | 284 | 13.3 MiB | 6.7 MiB |
| Private total | 334 | 15.7 MiB | 7.8 MiB |
| Voice prefix, 10 s | 125 | 5.9 MiB | 2.9 MiB |
| Decoder ring, context 250 | 250 | 1.9 MiB | 1.0 MiB |

The decoder cache is the important detail. The code allocates `mimi_sequence_length = max_gen_len * 16`, which is about 4,544 frames for a 50-token chunk. The decoder only uses a 250-frame context. The full allocation is about 37 MiB FP32 per request. A ring buffer of 250 frames uses about 2 MiB. This is a 35 MiB saving per request.

The voice prefix is also copied for each request. With a long voice prompt, this is the dominant memory cost. Share the prefix or truncate it to 10 to 15 seconds.

### 3.3 Current per-frame host syncs

The following calls force a device-to-host sync:

| Location | Call | Frequency |
| --- | --- | --- |
| `modules/attention.py:14` | `int(offset.view(-1)[0].item())` | Per layer, per frame |
| `modules/attention.py:110` | `bool((pad > 0).any())` | Per layer, per frame |
| `models/tts_model.py:988` | `is_eos.item()` | Per frame |
| `models/tts_model.py:507` | `int(offset.view(-1)[0].item())` | Per chunk |

With 6 layers, the first two cause 12 syncs per frame. The EOS check adds one. This makes CUDA graphs impossible and adds large jitter. It also serializes the GPU pipeline.

The timing log is misleading on GPU. `display_execution_time` uses `time.monotonic()` around asynchronous launches. It measures launch time, not completion, unless a later `.item()` forces a sync.

### 3.4 Current per-frame waste

| Location | Work | Why it is waste |
| --- | --- | --- |
| `modules/rope.py:25-44` | Builds `arange`, `exp`, `cos`, `sin` for every layer, every frame | These tables depend only on position and dimension. Precompute them. |
| `modules/attention.py:210-214` | Builds a causal mask for every layer, every frame | With a single query at the end of the cache, all cached keys are valid. No mask is needed without padding. |
| `models/flow_lm.py:158` | `torch.where(torch.isnan(sequence), ...)` | Only the BOS input is NaN. Handle BOS once. |
| `models/flow_lm.py:162` | `transformer_out.to(torch.float32)` | Forces an FP32 flow head and an extra cast. Keep the head in FP32 only if quality needs it. |
| `models/flow_lm.py:170-174` | Allocates and samples noise every frame | Pre-generate a noise block per request. This is also required for CUDA graphs. |
| `models/tts_model.py:823` | `copy.deepcopy(model_state)` per request | Copies the full voice KV cache. |
| `models/tts_model.py:834` | Decoder cache sized to full generation | Over-allocates by about 18x. Use the 250-frame context. |
| `models/tts_model.py:841,956` | Two threads per request | Does not scale. Use one scheduler and batched workers. |
| `models/tts_model.py:1015` | `lru_cache(maxsize=2)` for voice states | Thrases with more than two voices. |
| `main.py:132` | One thread per HTTP request | Same scaling problem at the server layer. |
| `data/audio.py:95` | `.cpu().numpy()` per audio chunk | Forces a sync per chunk. Use pinned memory and async copy. |

## 4. Target architecture

### 4.1 One scheduler, not one thread per request

Replace the thread-per-request model with:

1. An async HTTP/WebSocket layer that puts requests into a queue.
2. One scheduler thread per GPU.
3. One decode worker per GPU, or a small fixed pool.
4. A batched step loop that advances all active requests by one frame.

The scheduler owns all model state. It never shares mutable state between threads. This removes GIL contention and makes batching possible.

### 4.2 Continuous batching

Batch these stages separately:

| Stage | Batch | Notes |
| --- | --- | --- |
| Voice encode | 1 to 4 | Only on cache miss. Keep off the critical path. |
| Text prefill | 4 to 16 | Variable length, pad and mask. |
| Frame decode | 32 to 128 | The main loop. All rows advance together. |
| Codec decode | 32 to 128 | Batch frames and rows. |
| Audio copy | Per request | Async pinned buffers. |

At each tick, every active row generates one frame. When a row reaches EOS, mask it out and compact the batch every N steps. Use a fixed maximum batch and a queue.

The existing `pad` field in `_LinearKVCacheBackend` is a good foundation. It right-aligns rows with different prefix lengths. The code already masks padded key positions. Keep that design, but remove the `bool((pad > 0).any())` sync.

### 4.3 Static buckets and CUDA graphs

The current Python loop cannot be captured because of dynamic slices and `.item()`. Use static buckets:

| Bucket | Use |
| --- | --- |
| Sequence 384 | Short prompts and short generations |
| Sequence 512 | Normal chunks |
| Sequence 768 | Long voice prefix or teacher forcing |
| Batch 1, 8, 16, 32, 64, 128 | Batch buckets |

For each batch and sequence bucket, capture one decode graph. Inside the graph:

1. Write the new K and V at a device offset with `index_copy_`.
2. Run attention over the full bucket with a key mask `arange < offset + 1`.
3. Run the FFN and flow head.
4. Write the output latent to a fixed buffer.
5. Copy the EOS flag to a device buffer.

Do not call `.item()` inside the graph. Read the EOS flag once every 4 to 8 frames. If EOS fired inside the block, trim the extra frames and honor `frames_after_eos`. This adds at most 8 extra frames of compute, about 640 ms of audio, but removes the per-frame sync.

The full-bucket attention costs more than a dynamic slice. At bucket 512 versus an average length of 300, it is about 1.7x more attention work. Attention is a small part of the 6-layer model, so this is a good trade. Use a smaller bucket for low-latency lanes.

### 4.4 KV cache and prefix sharing

Do these in order:

1. Truncate all voice prompts to 10 to 15 seconds by default. Quality is usually stable. Measure speaker similarity.
2. Precompute voice states with `export_model_state` and load the `.safetensors` file. This skips the Mimi encoder and the prompt prefill.
3. Raise the voice cache from 2 to 64 or 128 entries.
4. Share the read-only voice prefix across requests. Use one of these designs:
   - Group requests by voice and keep one shared prefix per group.
   - Use paged KV blocks with copy-on-write. The voice blocks are shared. The text and generated blocks are private.
5. Store the decoder cache as a 250-frame ring buffer. The decoder context is already 250.

If full paged attention is too much work, start with duplicated prefixes but no deep copy. The memory cost is acceptable for 50 to 100 streams. Add sharing when the voice count or prompt length grows.

### 4.5 Batched codec

The codec is currently decoded one request at a time in a worker thread. Batch it:

1. Collect one latent per active request.
2. Build a `[B, T, 32]` latent tensor.
3. Run `mimi.decode_from_latent` once for the batch.
4. Split the audio and copy each row to its stream.

The conv state modules already carry a batch dimension. `StreamingConv1d` and `StreamingConvTranspose1d` use `batch_size` in their state. The decoder transformer needs the same `pad` and offset treatment as the flow LM, but all rows start at offset 0 and advance together, so this is simpler than the flow LM.

For latency, decode the first frame alone for each new request, then decode 4 to 8 frames per call for throughput. Use separate CUDA graphs for 1, 4, and 8 frames.

### 4.6 Lowest-latency path

For a new request:

1. Look up the voice state. Do not encode the voice on the request path.
2. Prefill the text in a small, high-priority batch. Do not wait for a full decode batch.
3. Generate the first frame immediately.
4. Decode the first frame alone. Send the first PCM chunk as soon as it is ready.
5. Add the request to the main decode batch.

Use two lanes:

| Lane | Batch | Purpose |
| --- | --- | --- |
| Latency lane | 1 to 4 | New requests, prefill, first frame |
| Throughput lane | 32 to 128 | Steady-state decode |

The latency lane must preempt the throughput lane at step boundaries. Do not preempt in the middle of a graph.

## 5. T4 versus L4

| Item | Tesla T4 | NVIDIA L4 |
| --- | --- | --- |
| Architecture | Turing, sm75 | Ada, sm89 |
| Memory | 16 GB GDDR6 | 24 GB GDDR6 |
| Bandwidth | 320 GB/s | 300 GB/s |
| FP16 tensor | 65 TFLOPS | 121 TFLOPS |
| BF16 | No | Yes |
| TF32 | No | Yes |
| FP8 | No | Yes |
| FlashAttention-2 | No | Yes, through SDPA |
| Main limit | Syncs, launches, 16 GB | Memory is better, syncs still dominate |
| Recommended precision | FP16 weights and activations, FP32 flow head | BF16 or FP16, FP8 only after quality tests |
| Batch target | 32 to 64 | 64 to 128 |
| Attention path | SDPA memory-efficient or xformers | SDPA flash or xformers |
| Driver | Older images are common. Check CUDA 12.x support. | Needs a newer driver. Check before deployment. |

T4 notes:

- Do not use BF16 or FP8. They are not supported.
- FP16 is the main precision win. The flow head and EOS head can stay FP32.
- Turing has no FlashAttention-2. Test `xformers.ops.memory_efficient_attention` against SDPA. For small batches, the memory-efficient kernel can be faster.
- T4 has 16 GB. Cap the batch by measured KV memory, not by a fixed number.

L4 notes:

- The L4 has more compute, but at batch 1 it is memory and launch bound like the T4. The extra memory helps concurrency.
- BF16 is safer than FP16 for range. Test both. FP16 is usually fine for TTS.
- FP8 can cut weight bandwidth in half. Use it only on the FFN and attention projections, keep the flow head and codec in BF16 or FP16, and run the full quality suite.
- FlashAttention-2 through SDPA is available. Keep the K/V cache layout friendly to it. The current `[2, B, T, H, D]` cache is permuted to `[B, H, T, D]` at every step. A native `[B, H, T, D]` cache avoids the permute and gives a contiguous layout.

## 6. Memory and throughput model

Let `B` be the batch size. Let `t_s` be the time for one decode step for the whole batch. Each step produces 80 ms of audio per stream.

Per-stream real-time factor:

```
RTF = t_s / 80 ms
```

The service keeps up when `t_s <= 80 ms`. This is a weak limit. The useful limit is the target RTF, for example 0.1 for 10x real-time per stream.

Approximate compute per stream per frame:

| Part | GFLOP |
| --- | ---: |
| Flow transformer | 0.151 |
| Flow head | 0.020 |
| Decoder transformer, 16 steps | 0.202 |
| SEANet decoder | about 0.02 |
| Total | about 0.39 |

At batch 64:

```
64 * 0.39 = 25 GFLOP per step
```

At an effective 10 to 20 TFLOPS on T4, this is 1.2 to 2.5 ms of math. Add kernel overhead and you should target 3 to 6 ms per step. That gives a per-stream RTF of 0.04 to 0.08, or 12x to 25x real-time. On L4, target 2 to 4 ms.

Weights are read once per step. At FP16, that is about 219 MB per step. At 5 ms, that is 44 GB/s. This is well below the 300 to 320 GB/s limit. At batch 128, the weight read is amortized over more streams. The limit becomes compute and cache, not weight bandwidth.

Memory per stream with the fixes:

| Item | FP16 |
| --- | ---: |
| Private flow KV, 334 frames | 7.8 MiB |
| Decoder ring, 250 frames | 1.0 MiB |
| Conv state and buffers | 1 to 3 MiB |
| Audio buffer, 1 s | about 0.05 MiB |
| Total | about 10 to 12 MiB |

At 12 MiB per stream, 16 GB gives about 1,300 streams by memory alone. The practical limit is lower: 100 to 300 streams, set by scheduler overhead, kernel efficiency, and the latency SLO. The L4 has 24 GB, so memory allows more. Do not promise a number before measurement.

Without the fixes, a request can use 50 to 60 MiB, and a deep copy doubles the peak. That is the current concurrency ceiling.

## 7. Precision and quantization

Recommended order:

1. FP32 baseline on GPU. Record quality and latency.
2. FP16 transformer, FP32 flow head and codec. This is the safest big win.
3. FP16 codec. Test WER and speaker similarity.
4. BF16 on L4. Compare with FP16.
5. FP8 on L4 for FFN and attention only. Test carefully.
6. INT8 only if TensorRT calibration is available and quality holds.

Do not use `quantize=True` on GPU. The current path is CPU-only and raises on CUDA. The `torch.ao` dynamic int8 path is not a GPU solution.

For T4, FP16 is the practical ceiling. INT8 tensor cores exist, but dynamic quantization overhead and TTS quality risk make it a later experiment.

For L4, FP8 is the interesting option. The model is small and memory-bandwidth sensitive. FP8 weights halve the read traffic. Use per-tensor scaling and keep sensitive parts in higher precision. Do not quantize the flow head or the codec without a quality test.

## 8. Compiler and kernel options

Start with PyTorch, not TensorRT. The code changes are smaller and the debugging is easier.

### PyTorch path

1. Remove all host syncs.
2. Precompute RoPE tables.
3. Skip the attention mask when the query length is 1 and there is no padding.
4. Pre-generate noise.
5. Use static sequence and batch buckets.
6. Capture decode steps with CUDA graphs. `torch.compile(mode="reduce-overhead")` can do this, but manual graphs are more reliable for the KV cache.
7. Use `torch.inference_mode()`.
8. Set `torch.backends.cudnn.benchmark = True`.
9. On L4, set `torch.set_float32_matmul_precision("high")` for TF32 in FP32 fallbacks.

Do not expect `torch.compile` to fix the current code. The `.item()` and `.any()` calls cause graph breaks. Remove them first.

### TensorRT path

Use TensorRT only if the PyTorch path misses the target. A TensorRT engine for the per-frame transformer is feasible with static buckets and KV cache inputs and outputs. It can fuse the projections, LayerNorm, GELU, and RoPE. The decode loop, EOS logic, and scheduling stay in Python or C++.

The codec is also a good TensorRT candidate. It is convolutional, static, and batchable. A TensorRT FP16 codec can remove a large part of the kernel overhead.

Do not try to put the whole autoregressive loop into one TensorRT engine. The loop has control flow and per-request state.

### Attention kernels

| GPU | Option |
| --- | --- |
| T4 | SDPA memory-efficient, or xformers memory-efficient attention |
| L4 | SDPA flash, or xformers |
| Both | Native `[B, H, T, D]` KV layout, no per-step permute |

For paged prefix sharing, consider FlashInfer or a custom paged-attention kernel. This is a later step. Start with duplicated prefixes and a contiguous cache.

## 9. Serving and transport

- One process per GPU. Do not use multiple Uvicorn workers on one GPU. They duplicate the model and prevent batching.
- Use one scheduler per process. Use a router in front for multiple GPUs.
- Use an async endpoint. The current sync `def` endpoint runs in a thread pool.
- For lowest latency, use WebSocket with raw PCM16. HTTP chunked WAV is acceptable, but proxies and clients can buffer it.
- Disable proxy buffering. Set `TCP_NODELAY`.
- Send the first PCM chunk as soon as it is decoded. Keep `FIRST_CHUNK_LENGTH_SECONDS=0`.
- Add a small jitter buffer on the client, about 200 ms. Do not add it on the server.
- Use pinned memory and double buffering for audio copies. Overlap the copy with the next decode step.
- Warm up all CUDA graph buckets at startup. Run one dummy generation per bucket. This avoids first-request capture cost.
- Bake the weights, tokenizer, and voice states into the image. Set `HF_HUB_OFFLINE=1` at runtime.
- Set `OMP_NUM_THREADS=1` and `MKL_NUM_THREADS=1` for the GPU process.

## 10. Benchmark plan

Measure these:

| Metric | Definition | Target |
| --- | --- | --- |
| TTFA p50 | Request to first PCM byte | 100 to 200 ms |
| TTFA p95 | Request to first PCM byte | under 300 ms |
| Inter-chunk gap p95 | Time between PCM chunks | under 80 ms |
| RTF per stream | Generation time / audio time | under 0.1 |
| Max streams | Streams at RTF <= 1 and TTFA p95 <= 300 ms | measure |
| GPU memory | Peak per stream and total | under 90 percent |
| Sync count | Host syncs per frame | 0 in the decode loop |
| Kernel count | Launches per frame | under 50 after graphs |

Workloads:

1. Short text, 10 words, one chunk.
2. Medium text, 50 tokens, one chunk.
3. Long text, 200 tokens, four chunks.
4. Same voice, 1, 8, 32, 64, 128 streams.
5. Different voices, 1, 8, 32, 64 streams.
6. Code-mixed English and Hindi.
7. Each of the 7 languages.

Quality set:

- Sarvam dub benchmark, 64 clips per language, as used in the model card.
- WER with Whisper large-v3 for English and Indic Transcribe for the other languages.
- Speaker similarity with WavLM.
- UTMOS.
- A fixed 20-sentence golden set per language for regression.

Acceptance gates for any precision or kernel change:

- WER increase no more than 0.5 percentage points absolute.
- Speaker similarity drop no more than 0.01.
- UTMOS drop no more than 0.05.
- No new clicks, dropouts, or chunk-boundary artifacts.

Use Nsight Systems to find gaps. Look for `cudaStreamSynchronize`, `cudaMemcpy`, and long kernel launch gaps. Use `torch.profiler` for the Python side. Measure with CUDA events, not `time.monotonic()` around async launches.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| FP16 changes prosody or WER | Keep the flow head and codec FP32 first. Run the full quality set. |
| FP8 hurts Indic quality | Limit FP8 to FFN and attention. Keep the codec and flow head in BF16. |
| Batched padding leaks into attention | Test single versus batched outputs with the same seed. Check pad masks. |
| CUDA graph captures a stale offset | Use device offsets and `index_copy_`. Do not bake Python offsets. |
| Continuous batching starves new requests | Use a latency lane and a prefill priority. |
| Long voice prompts use too much memory | Truncate to 10 to 15 s. Share prefixes. |
| Voice clone cache thrash | Precompute and persist voice states. Raise the cache size. |
| T4 driver or CUDA mismatch | Pin a known-good torch and CUDA pair. Test on the target image. |
| TensorRT engine build complexity | Treat it as phase 3, after the PyTorch path. |

## 12. Phased roadmap

### Phase 1: Remove the obvious GPU blockers

Duration: 3 to 5 days.

1. Remove the `.item()` in `complete_kv`. Pass the offset as a Python int from the scheduler.
2. Remove `bool((pad > 0).any())`. Keep a Python flag that says whether the batch has padding.
3. Precompute RoPE tables up to the maximum bucket. Slice by offset.
4. Skip the attention mask when the query length is 1 and there is no padding.
5. Pre-generate a noise block for each request. Slice one row per frame.
6. Replace the per-frame `torch.isnan` with an explicit BOS path.
7. Truncate voice prompts to 10 to 15 seconds by default on the server.
8. Raise the voice cache to 64 entries.
9. Add a `--device cuda` path to `serve`. Move the model and decoder to the GPU.

Measure after each change. This phase alone should give a large latency reduction and make the step graph-safe.

### Phase 2: Batch and graph

Duration: 1 to 2 weeks.

1. Write a scheduler with a request queue, a latency lane, and a throughput lane.
2. Add batched text prefill with padding and masks.
3. Add batched frame decode for the flow LM.
4. Add batch support to the Mimi decode path.
5. Add a 250-frame ring buffer for the decoder KV cache.
6. Add static sequence and batch buckets.
7. Capture decode graphs with CUDA graphs.
8. Check EOS once per block of 4 to 8 frames.
9. Replace the per-request threads with the scheduler and a fixed worker pool.

### Phase 3: Memory and precision

Duration: 1 to 2 weeks.

1. Convert weights to FP16. Keep the flow head and codec FP32 first.
2. Test FP16 codec.
3. Share voice prefixes. Start with grouping by voice, then paged KV if needed.
4. Add async pinned audio copies.
5. Test BF16 on L4.
6. Test FP8 on L4 for FFN and attention.
7. Optional: TensorRT for the transformer step and codec.

## 13. Concrete patch list

Line numbers refer to commit `9e8413e`.

| Priority | File and line | Change | Expected impact |
| --- | --- | --- | --- |
| P0 | `modules/attention.py:14` | Remove `offset.item()`. Use a Python int offset. | Removes 6 syncs per frame. Enables graphs. |
| P0 | `modules/attention.py:110` | Remove `bool((pad > 0).any())`. Use a Python `has_pad` flag. | Removes 6 syncs per frame. |
| P0 | `models/tts_model.py:988` | Remove `is_eos.item()`. Check a device flag once per block. | Removes 1 sync per frame. Enables graphs. |
| P0 | `modules/rope.py:25-44` | Precompute cos and sin tables. Index by offset. | Removes many small kernels per layer. |
| P0 | `modules/attention.py:210-214` | Skip the mask when `t == 1` and no padding. | Removes mask construction per layer. |
| P0 | `models/flow_lm.py:158` | Handle BOS explicitly. Do not run `isnan` every frame. | Removes one kernel per frame. |
| P0 | `models/flow_lm.py:170-174` | Pre-generate noise blocks. Slice per frame. | Removes RNG kernel per frame. Graph-safe. |
| P0 | `models/tts_model.py:823` | Do not deep-copy the full state. Use a pooled per-request state. | Less memory and copy time. |
| P0 | `models/tts_model.py:834` | Use the 250-frame decoder context, not the full generation length. | Saves about 35 MiB per request. |
| P0 | `models/tts_model.py:1015` | Raise the voice cache from 2 to 64 or 128. | Fewer voice encodes. |
| P1 | `models/tts_model.py:841,956` | Replace per-request threads with a scheduler. | Enables batching. Less GIL contention. |
| P1 | `main.py:132` | Replace the per-request thread with an async queue. | Same. |
| P1 | `models/tts_model.py:514` | Batch the Mimi decoder. | Higher codec throughput. |
| P1 | `modules/attention.py:93` | Add a native `[B, H, T, D]` cache layout. | No per-step permute. Better attention kernel. |
| P1 | `data/audio.py:95` | Use pinned memory and async copy. | Removes a sync per audio chunk. |
| P2 | `utils/config.py` and configs | Add a `dtype` path for FP16 weights. | 1.5x to 2x less memory and faster math. |
| P2 | `models/tts_model.py` | Add an optional FP16 codec path. | Faster decode. |
| P2 | new module | Static bucket scheduler and CUDA graph capture. | Removes launch overhead. |
| P2 | new module | Shared voice prefix or paged KV. | 3x to 5x more streams. |
| P3 | `pocket_tts/quantization.py` | Add a GPU FP8/INT8 path. | L4 only. Test quality. |
| P3 | new module | TensorRT engine for the transformer and codec. | Only if PyTorch misses the target. |

## 14. What not to do

- Do not run multiple model replicas on one GPU. Batch instead.
- Do not use `quantize=True` on CUDA. It is CPU-only.
- Do not use dynamic shapes with CUDA graphs. Use buckets.
- Do not check EOS every frame on the host. Check it in blocks.
- Do not copy the full voice KV cache per request.
- Do not size the decoder cache to the full generation.
- Do not add more threads. Add batching.
- Do not quantize the codec to FP8 without a listening test.

## 15. Open questions

1. What is the target concurrency? 50, 100, or 200 streams per GPU?
2. Is the voice set fixed? If yes, precompute and share all voice prefixes.
3. What is the typical text length? One sentence or several paragraphs?
4. Is the client HTTP or WebSocket? What jitter buffer does it use?
5. What are the target T4 and L4 driver and CUDA versions?
6. What quality loss is acceptable for FP16 and FP8?
7. Is the multilingual model the only target, or must the English models also work?
8. Do you need reproducible output, or is fresh noise per request acceptable?

## 16. Bottom line

The model is a good fit for high-concurrency GPU serving. It is small, streamable, and uses only 80 ms per frame. The current runtime is not the right shape for the job.

Do Phase 1 first. Removing the host syncs and the per-frame mask and RoPE work is low risk and gives a large latency win. Then build the batched scheduler and CUDA graphs. Then add prefix sharing and precision tuning.

A realistic target after Phase 1 and Phase 2:

- First audio: 100 to 250 ms p50 on T4 and L4.
- Per-stream speed: 10x to 25x real-time at moderate batch.
- Concurrency: 50 to 150 streams per T4, 100 to 200 per L4, after measurement.
- No per-frame host syncs in the decode loop.

The biggest risk is not the model. It is the serving architecture. Fix that first.
