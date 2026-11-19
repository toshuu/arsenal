---
type: CODING
time: 2026-11-20T00:40:00+05:30
summary: Diagnose post-dislike regressions, recover the 32-client gate, and define the 224-client limit.
paths: Code/batch/server.py; Code/batch/batched_stream.py; Code/probes/probe_http_load.py; Skeletons/Code/batch/server.py; Skeletons/Probes/probe_http_load_224.md; Ideas/IDEA-0005-long-text-and-production-readiness.md; .stageset/facts.md
related: IDEA-0005; FACT-0109; FACT-0110; FACT-0111; FACT-0112; FACT-0113
commit: -
remote: -
branch: -
---

# Session notes

## Owner context

- Dislike point: `2026-11-19T20:50:20+05:30` (FACT-0109).
- Baseline before dislike point: direct B=224, conditioned, p95 112.2 ms, RTF 0.824 (FACT-0064). 30-burst p95 119.9 ms (FACT-0087).
- After dislike point, some HTTP runs reported 6–13 s at 224 clients. The owner asked to find and fix bad behavior.

## What was wrong (post-dislike regressions)

1. **Probe artifact.** `probe_http_load.py` lost `httpx.Limits` and did not read `ARSENAL_LOAD_LIMITS`. 224 clients used a small default pool. Client connection wait increased.
2. **Metric mismatch.** The 112 ms baseline is direct `BatchedStream` (in-process). The 6–13 s run is HTTP + queue + 224 sockets. The two runs are not equal.
3. **Grouping removed.** `BatchWorker._group_key()` returned `None`. All profiles mixed in one normal-path batch. The conditioned fast path was never used.
4. **Batch target cap.** `ARSENAL_BATCH_TARGET` default 32. A 224-client burst split into 7 serial batches.
5. **Per-row conditioner cost.** `_build_prefixes_with_voices()` called the conditioner once per row. 224 rows = 224 GPU calls.
6. **Event-loop block.** `chunks_for()` tokenized in the event loop. 224 requests blocked the loop.

## What was not the cause

- The model did not regress. Direct B=224 first emit is 97.7 ms (FACT-0111).
- B=224 memory fit is still valid (FACT-0102). RTF stays below 1.0.
- The 32-client gate behavior was valid in earlier runs. The fix keeps and proves it.

## What was fixed (how)

- `probe_http_load.py`: async client, start barrier, warm pool, `ARSENAL_LOAD_LIMITS`, per-request header/first timing.
- `server.py`: drain-first admission (take all waiting jobs, then use the time window). Hybrid grouping (one profile id → conditioned path; mixed ids → one normal-path batch). Default `max_batch=224`, default window `150` ms. `chunks_for()` moved to a worker thread. `request_first_chunk_ms` metric added.
- `batched_stream.py`: per-row voice prefill uses one batched conditioner call. Text chunk results are cached.

## Results

| Case | Path | Result | Evidence |
| --- | --- | --- | --- |
| Direct B=224, conditioned | `probe_ttfa_stages.py` | PASS, p95 97.7 ms, 672/672 < 350 | FACT-0111 |
| 32 clients, mixed profiles, HTTP | `probe_http_load.py` | PASS, client p95 340.6 ms, server 294.0 ms, 0 err | FACT-0110 |
| 224 clients, 1 profile, HTTP | `probe_http_load.py` | FAIL, client p95 7379 ms, server p95 3166 ms (window 700), 0 err | FACT-0112 |

## What is not solved

- 224-client HTTP p95 is above 350 ms. The gate is not met.
- Server-side p95 is still high when clients arrive over time.
- A job that arrives after a batch starts waits for batch end.

## Real-life issues

1. **Head-of-line blocking.** One GPU runs one batch to completion. Late first-chunk jobs wait 0.5–2 s. Continuous batching can remove this. It needs dynamic KV/Mimi state changes. High risk.
2. **HTTP ingress on 4 vCPU.** 224 sockets and one event loop spread arrivals. Client first-byte time is 3–4 s after server send in this host.
3. **Probe/server CPU contention.** Load generator and server share 4 vCPU. Production uses separate hosts.
4. **Batch/window tuning is workload-specific.** Small window starts early but can split a burst. Large window collects but delays start.
5. **Continuous batching, per-row RoPE, and shared voice KV** are not implemented. Owner permission is required.

## Follow-up

- Keep 32-client HTTP as the active production gate.
- Record direct B=224 model runs in every comparison.
- Next code option: continuous batching (admit rows at frame boundaries). Plan as a new skeleton before code.
