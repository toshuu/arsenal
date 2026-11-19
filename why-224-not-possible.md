# Why B=224 HTTP is not reached (yet)

Date: 2026-11-20 (Asia/Kolkata)  
Project: Arsenal / Kyutai Pocket TTS on one NVIDIA T4  
Purpose: Explain why 224 concurrent HTTP clients do not reach p95 first-chunk <= 350 ms. Give full context for solution design.

## 1. Goal

| Metric | Target |
| --- | --- |
| Concurrent streams (B) | 224 (or maximum possible) |
| Client first-chunk p95 | <= 350 ms |
| Server `request_first_chunk_ms` p95 | <= 350 ms |
| Errors | 0 |
| Sustained RTF | < 1.0 |
| Wall time | Minimum to finish all B |

Reference: direct in-process model does B=224 first emit at p95 97.7 ms (672/672 < 350 ms, RTF 0.824 earlier, FACT-0111 / FACT-0064). The gap is in the HTTP serving path, not in model compute.

## 2. Environment and stack

| Item | Value |
| --- | --- |
| GPU | 1x NVIDIA Tesla T4, 15360 MiB |
| CPU (test host) | 4 vCPU (shared). Server and load generator ran on same host, pinned to different cores (server 0,1; probe 2,3) |
| Model | Kyutai Pocket TTS (`pocket-tts`), FP16 backbone/Mimi weights, conditioned voice profile path available |
| B=224 memory | Safe at `max_frames=192`: 12.303 GiB allocated, 1.952 GiB free (FACT-0102) |
| Server | `Code/batch/server.py` (FastAPI + uvicorn, 1 worker, `uvloop`, `httptools`, backlog 1024, access log off) |
| Batch engine | `Code/batch/batched_stream.py` (`BatchedStream.stream`, lockstep generation over fixed batch rows) |
| Probe | `Code/probes/probe_http_load.py` (async `httpx`, warm keep-alive pool, start barrier, `ARSENAL_LOAD_LIMITS>=B`) |
| Endpoints | `POST /tts`, `POST /tts/stream` (raw `audio/L16`, chunked), `POST /tts/batch`, `/health`, `/metrics` |

## 3. Metric definitions

| Metric | Definition |
| --- | --- |
| Client first-chunk p95 | Time from client request send (after barrier/sleep) to first received audio byte, p95 over requests |
| Server `request_first_chunk_ms` p95 | Time from HTTP handler entry (`request_start`) to first chunk ready for that request, p95, reported in `/metrics` |
| Queue p95 | Time from job submit to job/batch start in worker queue, p95 |
| RTF | Burst wall time / total generated audio seconds |

`request_first_chunk_ms` is the primary server-side gate. Client time includes network/loop/host contention.

## 4. Timeline and fixes

| Date (IST) | Event | Evidence |
| --- | --- | --- |
| 2026-11-16 | Direct baseline: B=224 conditioned p95 112.2 ms, RTF 0.824; soak p95 119.9 ms | FACT-0064, FACT-0087 |
| 2026-11-19 20:50:20 | Owner dislike point. Post-point HTTP changes caused 6–13 s B=224 runs | FACT-0109 |
| 2026-11-20 | Recheck direct: B=224 p95 97.7 ms (no model regression) | FACT-0111 |
| 2026-11-20 | Recovery fixes: async probe + `ARSENAL_LOAD_LIMITS`, drain-first batching, hybrid profile grouping (uniform conditioned, mixed normal), 1 batched conditioner call for per-row voices (not 224 calls), chunk cache, `chunks_for` off event loop, `request_first_chunk_ms`, default `max_batch=224`, window 150 ms | commit `fcd4253`, FACT-0113 |
| 2026-11-20 | 32-client HTTP PASS: client 340.6 ms, server 294.0 ms, 0 err | FACT-0110, run `20261120-001820-RUN` |
| 2026-11-20 | 224-client HTTP FAIL (single profile): client 7379 ms, server 3166 ms (window 700) | FACT-0112, run `20261120-001821-RUN` |
| 2026-11-20 01:33:15 | Steps 1,2,4 ramp + window sweep. Max pass B=37. B=224 best server 1542.1 ms | commit `e6c8153`/`f1d0f51`, FACT-0115, FACT-0116, runs `20261120-013315-RUN*` |

### Regressions found and fixed (post-dislike)

| Issue | Effect | Fix |
| --- | --- | --- |
| Probe lost `httpx.Limits`, no `ARSENAL_LOAD_LIMITS` | Client pool capped; connection wait inflated | Async client, warm pool, barrier, limits >= B |
| Metric mismatch | Direct 112 ms compared to HTTP 13 s | Compare equal paths; track server/client separately |
| `_group_key()` returned `None` | All profiles mixed -> normal path, conditioned fast path never used | Hybrid: one profile id -> conditioned; mixed ids -> one normal batch |
| `ARSENAL_BATCH_TARGET` default 32 | 224 burst split into serial batches | Drain-first admission, target/max tuned |
| `_build_prefixes_with_voices` per-row conditioner | 224 GPU calls per mixed batch | 1 batched conditioner call |
| `chunks_for` in event loop | 224 requests blocked uvicorn loop | Run in worker thread (`to_thread`) |

## 5. Current measured results (Steps 1,2,4)

Setup: 1 T4, 4 vCPU shared. Server cores 0,1 (uvloop/httptools). Probe cores 2,3. 1 conditioned profile `v1`, warm keep-alive, barrier, 2 bursts, `max_batch=max_rows=batch_target=B`, `ARSENAL_LOAD_LIMITS=256`.

### 5.1 Ramp: max passing B

| B | Window (ms) | Server p95 (ms) | Client p95 (ms) | Queue p95 (ms) | Errors | RTF max | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 32 | 150 | 279.9 | 327.2 | 150.5 | 0 | 0.038 | PASS |
| 36 | 150 | 253.8 | 310.5 | 150.3 | 0 | 0.029 | PASS |
| 37 | 150 | 241.0 | 315.0 | 148.7 | 0 | 0.030 | PASS |
| 38 | 150 | 1802.3 | 1979.3 | 150.6 | 0 | 0.032 | FAIL |

**Max B (server and client p95 <= 350 ms): 37. Best window for B<=37: 150 ms.**

### 5.2 B=48 (best tested window)

| B | Window (ms) | Server p95 (ms) | Client p95 (ms) | Queue p95 (ms) | Errors | RTF max | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 48 | 5 | 1088.6 | 1199.7 | 1365.9 | 0 | 0.037 | FAIL |

Windows 0,10,20,50,150 were worse or also failed.

### 5.3 B=224 window sweep

| B | Window (ms) | Server p95 (ms) | Client p95 (ms) | Queue p95 (ms) | Errors | RTF max | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 224 | 5 | 1963.2 | 5752.4 | 3117.2 | 1 | 0.030 | FAIL |
| 224 | 10 | 1542.1 | 5627.9 | 3692.7 | 0 | 0.028 | FAIL (best server) |
| 224 | 20 | 2336.7 | 5792.4 | 3579.0 | 0 | 0.028 | FAIL |
| 224 | 50 | 2364.0 | 6408.3 | 1961.1 | 2 | 0.028 | FAIL |
| 224 | 100 | 1699.4 | 5721.3 | 1296.8 | 1 | 0.025 | FAIL |
| 224 | 150 | 2317.2 | 6480.8 | 1900.5 | 1 | 0.027 | FAIL |

**B=224 best server p95: 1542.1 ms (+1192 ms vs 350). Client p95: 5627.9 ms. No window passed.**

### 5.4 B=208 (sample)

| B | Window (ms) | Server p95 (ms) | Client p95 (ms) | Queue p95 (ms) | Errors | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 208 | 10 | 1789.4 | 6150.9 | 1863.7 | 2 | FAIL |
| 208 | 50 | 2177.7 | 6110.7 | 1897.2 | 1 | FAIL |

## 6. Why B=224 is not reached

### 6.1 Not the cause

| Area | Evidence |
| --- | --- |
| Model compute | Direct B=224 first emit p95 97.7 ms (FACT-0111). Model can produce first audio fast. |
| GPU memory | B=224, `max_frames=192`: 12.303 GiB allocated, 1.952 GiB free (FACT-0102). |
| Sustained throughput | RTF 0.02–0.03 in B=224 HTTP runs. GPU keeps up. |
| Model errors | 0 errors in best-server B=224 run; occasional client/probe errors in some runs but not the latency root cause. |

### 6.2 Causes (timeline-diagnosed, FACT-0117)

Per-request timeline (`ARSENAL_TIMELINE=1`, pinned server 0,1 / probe 2,3, 1 conditioned profile, w150) named the jumping stage:

| Path / B | req or srv p95 (ms) | queue/`submit_to_batch_start` p95 (ms) | Note |
| --- | ---: | ---: | --- |
| No-HTTP B37 | req 90.4 | q 1.7 | `BatchWorker` direct, 1 batch |
| No-HTTP B38 | req 95.7 | q 1.9 | `BatchWorker` direct, 1 batch |
| No-HTTP B48 | req 104.7 | q 2.3 | `BatchWorker` direct, 1 batch |
| HTTP B37 | srv 288.8, cli 357.3 | submit->batch_start 111.7 | borderline |
| HTTP B38 | srv 2403.3, cli 2614.0 | submit->batch_start 2272.5 | cliff |
| HTTP B224 | srv 1473–2138, cli 4911–5679 | submit->batch_start 1813+ | FAIL, range over configs |

1. **Host CPU contention/scheduling starvation (primary, evidenced).**  
   On 4 shared vCPU, `submit_to_batch_start_ms` jumps to ~1.8–2.3 s at B>=38 while no-HTTP queue/exec stays ~2/96 ms. `top -H` during B=224 burst shows probe ~100% CPU and server batch thread starved/contending. Server, uvicorn loop, and probe compete for cores; requests wait before batch execution even when batch/model can complete fast once running.

2. **Head-of-line blocking / batch serialization (contributing at high B).**  
   `BatchWorker` executes one collected batch to completion (`BatchedStream.stream` over fixed rows). At B=224 this yields large queue tails and client tails, but timeline shows the dominant jump is pre-execution wait under contention rather than model micro-stages (B38: batch_start->stream_start 2.5 ms, cond->flow0 54.6 ms, flow0->mimi0 98.7 ms p95).

3. **Admission/window trade-off (no good setting at B=224).**  
   Small windows start early but can split/queue behind batches; large windows delay start. No tested window reached <= 350 ms at B=224 (best srv 1542 ms at w10 in FACT-0116 / 1473 ms in later sample).

4. **Ingress spread and same-host probe contention.**  
   224 HTTP requests traverse one uvicorn loop on shared CPU. Even with async client, warm keep-alive, barrier, and `chunks_for` offloaded, arrival/handling spreads and client p95 far exceeds server p95 at B=224 (e.g. cli 5628 vs srv 1542 ms).

5. **Not model compute.**  
   Direct B=224 first emit p95 97.7 ms (FACT-0111); no-HTTP B=38/B=48 fast.

### 6.3 Why B<=37 passes (and B=38 is unstable)

At B<=37 with window 150 ms, requests arrive/submit before execution without large starvation, queue/submit->batch_start stays ~90–151 ms p95, and first byte completes within budget (server ~241–302 ms, client ~310–357 ms in measured runs). B=38 is a boundary/unstable point on this host: observed as 335 ms srv in one sample and 2403 ms in another (`submit_to_batch_start` 2272 ms) with the same nominal setup, consistent with CPU scheduling contention rather than a deterministic model-cost step. Reliable proven max remains **36–37** (FACT-0115). Unpinned + `ARSENAL_TORCH_THREADS=1|2` showed no safe improvement (B32/37 regressions/instability).

## 7. What was tried (and kept)

| Step | Action | Result |
| --- | --- | --- |
| Probe | `ARSENAL_LOAD_LIMITS`, async client, warm keep-alive, start barrier, separate process | Kept |
| Server | 1 uvicorn worker, uvloop, httptools, backlog 1024, no access log | Kept |
| Host | Probe cores 2,3; server cores 0,1 (`taskset`) | Kept |
| Admission | Drain-first batching, window fallback, window sweep 0–150 ms | Kept; best 150 ms for B<=37, no B=224 pass |
| Grouping | Uniform profile -> conditioned path; mixed -> one normal batch | Kept |
| Engine | 1 batched conditioner call per mixed batch, chunk cache, `chunks_for` off event loop | Kept |
| Step 2 A/B | uvloop/httptools vs asyncio/h11 | No clear gain; uvloop/httptools kept |
| Step 3 | Continuous batching | **Not implemented**. Plan only; requires approval and state redesign |

## 8. Current architecture constraints (relevant to solution)

- **One GPU, one model process.** Multi-worker uvicorn would load multiple models (not feasible). Two processes on one T4 previously performed worse.
- **Lockstep batch generation.** `BatchedStream.stream` runs a fixed set of rows through frame steps until completion. Rows/texts differ in length; EOS handled per row, but batch membership is fixed at start.
- **One job = one text chunk.** `/tts/stream` submits chunks sequentially per request; continuations have lower priority than first chunks.
- **State.** Batch uses model/KV/Mimi state sized for the active batch and `max_frames`. Admitting a new row mid-generation requires dynamic state growth or pre-allocation and careful indexing.
- **Conditioned path.** Fast path requires one profile and uniform first-chunk token-length conditions in current design; mixed cases fall back to normal path.

## 9. Constraints (do not violate without approval)

- No second model worker per T4.
- No CUDA graphs by default.
- No per-row RoPE or shared voice KV without owner permission.
- No continuous-batching code without a reviewed skeleton/plan and approval.
- Do not claim B=224 HTTP pass without saved evidence (server p95, client p95, errors, RTF).

## 10. Open questions for a solution designer

1. **Continuous batching:** Can first-chunk jobs be admitted at chunk/frame boundaries without full-batch preemption? What KV cache and Mimi decoder state structures must be resized or pre-allocated? What is the per-step overhead?
2. **Admission:** Is there a better policy than drain+window for bursty arrivals on a slow ingress host (e.g. target-count wait with hard cap, or adaptive window)?
3. **Host separation:** If probe runs on a separate machine, does client p95 approach server p95 at B=224? (Server p95 still 1542 ms in best tested case.)
4. **Chunking/priorities:** Can continuations be paused/yielded to serve waiting first chunks, given one-chunk-per-job and stream semantics?
5. **Alternative serving:** Would a different HTTP/runtime model (e.g. dedicated accept thread/process, HTTP/2, or different async server) reduce ingress spread enough on 4 vCPU?
6. **Model/batch shape:** Can a smaller effective first-response batch or staged prefill reduce first-chunk latency while preserving throughput?

## 11. Evidence and file map

| Artifact | Path |
| --- | --- |
| This report | `why-224-not-possible.md` |
| Direct B=224 model proof | `probes/out/ttfa_b224_direct.json`, FACT-0111 |
| 32-client HTTP pass | `probes/out/probe_b32_async_final.json`, FACT-0110 |
| 224-client HTTP fail | `probes/out/probe_b224_async_single.json`, `probes/out/probe_b224_async_single_w50.json`, FACT-0112 |
| Step 1/4 ramp data | `probes/out/sweep_b32_s14.json`, `probes/out/sweep_b36_s14.json`, `probes/out/ramp_exact_s14.json`, `probes/out/sweep_b48_s1.json`, `probes/out/sweep_b40_s1.json`, `probes/out/sweep_b224_s4.json`, `probes/out/step2_b32.json` |
| Run reports | `.stageset/runs/20261120-001820-RUN.md`, `20261120-001821-RUN.md`, `20261120-001821-RUN-02.md`, `20261120-013315-RUN.md`, `20261120-013315-RUN-02.md` |
| Facts | `.stageset/facts.md` (FACT-0064, 0087, 0102, 0109–0116) |
| Design docs | `Ideas/IDEA-0005-long-text-and-production-readiness.md` (§17–19), `.stageset/sessions/coding-burst-recovery.md`, `.stageset/sessions/coding-b224-ramp.md` |
| Code | `Code/batch/server.py`, `Code/batch/batched_stream.py`, `Code/probes/probe_http_load.py`, `Code/probes/ramp_b.py` |

## 12. Bottom line

- **Model:** B=224 is feasible at ~98 ms first emit.
- **HTTP today:** max proven B with p95 <= 350 ms is **37** (server 241 ms, client 315 ms) on this 4-vCPU T4 host.
- **B=224 HTTP:** not reached. Best server p95 1542 ms (w10), client 5627 ms, RTF OK. Main blockers: head-of-line blocking, admission/ingress spread, and host contention. Continuous batching is the leading untried code fix but requires state-management redesign and approval.


## 13. Next levers (READY plan, no code)

Status: **READY plan**. No implementation in this run. Step 3 continuous batching remains **NO-GO on this host** given FACT-0117 evidence (CPU starvation).

1. **Separate probe host (isolate server CPU).**  
   Run load generator from a different machine/network path so the server owns all 4 vCPU. Re-measure client p95 vs server p95 and re-ramp B. Goal: remove same-host probe contention and determine true ingress/serving ceiling.
2. **Reduce per-request server CPU cost.**  
   Minimize per-request threads, callbacks, allocations, and parsing in the HTTP hot path; prefer one ingress/submit queue path and lightweight request handling. Keep `ARSENAL_TIMELINE=0` in production measurements. Validate no regression at B=32/37 before keeping.
3. **More CPU / re-test on >=8 vCPU host.**  
   Repeat ramp on a host with more (or isolated) CPU capacity to eliminate scheduling starvation, then reassess window/admission and only then revisit Step 3 continuous-batching skeleton with evidence.
