# Burst concurrency report: TTFA under 350 ms

Date: 2026-11-15
Model: pocket-tts multilingual, 109.5M params, FP32
Hardware: 2x Tesla T4 15 GB, 4 vCPU
Runtime: current upstream code, no batching, process-per-request

## Answer

| Setup | Max concurrent requests with p95 TTFA <= 350 ms | Share under 350 ms |
|---|---|---|
| 1x T4 | **4** | 32/32 = 100% |
| 2x T4 | **5** | 15/15 = 100% |

With the current runtime, one T4 handles **4** simultaneous requests. Two T4s handle **5**.
A second GPU adds only one request. At 6 or more, the tail breaks 350 ms.

TTFA means time to the first non-silent audio chunk. It does not include network time.

## Why two GPUs do not double the number

The runtime is CPU-bound, not GPU-bound.

- Each request uses one Python generation loop plus one decoder thread.
- 4 vCPUs must run all request threads.
- At 6 requests there are 12+ runnable threads. Scheduling delay becomes the tail.
- GPU use stays low while TTFA rises. The second GPU cannot fix CPU contention.

## Single T4 results

| N | p50 ms | p95 ms | Under 350 ms | Runs |
|---|---|---|---|---|
| 1 | 55.6 | 55.6 | 100% | 1 |
| 2 | 87.7 | 87.7 | 100% | 1 |
| 3 | 98.8 | 100.1 | 100% | 1 |
| **4** | **107-112** | **306-332** | **32/32 = 100%** | **8 bursts** |
| 5 | 152.5 | 428.8 | 12/15 = 80% | 3 |
| 6 | 185.9-240.1 | 249.5-510.5 | 14/18 = 78% | 3 |
| 7 | 237.1 | 578.9 | 14/21 = 67% | 3 |
| 8 | 227-268 | 282-565 | 17/24 = 71% | 3 |
| 10 | 373.2 | 748.6 | fail | 1 |
| 12 | 373.3 | 923.4 | fail | 1 |

N=4 is stable: 8 bursts, 32 requests, all under 350 ms.
N=5 and above are unstable. One early N=6 burst passed at p95 249 ms, but repeats did not.

## Phase B: lockstep batched server on one T4

Runtime: one process, one model copy, one lockstep batch. Streaming on. Unique text per request. FP32.
Texts: unique sentences, one text chunk per row, temp 0.3.
Voice: `Code/probes/ref/voice.wav` (6.48 s, 24 kHz).
Output: `Code/probes/out/bench_batch_server_knee.json`.

| Batch | p50 ms | p95 ms | max ms | under 350 ms | wall s | RTF | VRAM MB |
|---|---|---|---|---|---|---|---|
| **30** | 222.4 | 278.8 | 375.8 | 149/150 | 2.42 | 0.013 | 2137 |
| **32** | 260.1 | 327.0 | 404.8 | 156/160 | 2.56 | 0.013 | 2247 |
| 34 | 280.0 | 359.7 | 398.0 | 160/170 | 2.81 | 0.013 | 2360 |
| 35 | 285.8 | 358.5 | 438.4 | 165/175 | 2.88 | 0.013 | 2416 |
| 36 | 290.8 | 357.6 | 432.1 | 168/180 | 2.94 | 0.013 | 2476 |

Parity B=32 vs B=1 at temp 0: max abs diff 1.07e-04, correlation 1.0.

B=30 passes p95 with 99.3% under 350 ms. B=32 passes p95 with 97.5% under 350 ms, but some rows exceed 350 ms. B=34-36 fail p95. B=34 was 295.0 ms in one run but 359.7 ms in another, so it is not stable.

One batched T4 server supports **30** requests safely and **32** at the measured p95 ceiling. That is **7.5x to 8x** the baseline of 4 concurrent requests.

## Two T4 results

| N | p50 ms | p95 ms | Under 350 ms | Runs |
|---|---|---|---|---|
| 4 | 95.9 | 281.3 | 12/12 = 100% | 3 |
| **5** | **131.4** | **175.2** | **15/15 = 100%** | **3** |
| 6 | 173.7 | 462.9 | 16/18 = 89% | 3 |
| 8 | 216-252 | 425-656 | fail | 4 |
| 12 | 376.1 | 1024.5 | fail | 1 |
| 16 | 511.0 | 1342.6 | fail | 1 |

Balanced placement: requests go to GPU 0 and GPU 1 in turn.

## Method

- Each request runs in its own process with its own model copy on a T4.
- Model and voice state load before the burst. Load time is not in TTFA.
- All workers wait on a barrier. They start together when the barrier opens.
- Each request uses the same short sentence, about 2.6 s of audio.
- Each request runs to completion to keep realistic load during the burst.
- Timer starts after the barrier. First sound is the first chunk with peak amplitude > 0.01.
- p95 uses all requests across all repeated bursts for that N.
- Measured at p50, p95, and p99. No errors and no OOM in any run.

Text: "Hello, this is a short test sentence."
Voice: `Code/probes/ref/voice.wav` (6.48 s, 24 kHz).
Output: `Code/probes/out/bench_burst_final.json`, `bench_burst_2gpu_final.json`.

## Caveats

- This is a process-per-request baseline, not a single batched server.
- A real server adds queueing and network time. The 350 ms budget must include them.
- p95 with small N is close to the max. Repeated bursts reduce this bias.
- The 2x T4 N=5 result has 15 samples. It is strong but not as repeated as N=4 on one GPU.
- Results are for one short sentence. Longer text raises prefill time.
- CPU speed and other load on the host can move the tail.

## What this means

The current runtime supports about **4 concurrent users per T4** at p95 TTFA <= 350 ms.
Two GPUs give only **5** because the host CPU saturates first.

This is the baseline to beat. The next design must:

1. Run one batched scheduler, not one process per request.
2. Batch the flow-LM step across requests.
3. Use one decoder thread or a vectorized decoder, not one thread per request.
4. Keep per-request Python work off the critical path.

Phase B met the target: one batched T4 server supports **30** requests safely and **32** at the measured p95 ceiling at p95 TTFA <= 350 ms. Baseline was 4 requests.

Next step: run the S1 FP16 spike (Phase C). Do not start TensorRT, ONNX, or shared voice KV without owner permission.
