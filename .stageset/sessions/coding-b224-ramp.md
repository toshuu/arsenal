---
type: CODING
time: 2026-11-20T01:33:15+05:30
summary: Steps 1,2,4 ramp and window sweep. Max HTTP pass B=37. B=224 still fails.
paths: Code/probes/probe_http_load.py; Code/probes/ramp_b.py; probes/out/sweep_b32_s14.json; probes/out/sweep_b36_s14.json; probes/out/sweep_b224_s4.json; probes/out/ramp_exact_s14.json
related: IDEA-0005; FACT-0111; FACT-0115; FACT-0116
commit: e6c8153
remote: origin
branch: main
---

# Session notes (2026-11-20T01:33:15+05:30)

## Setup

- 1 T4, 4 vCPU (shared).
- Server: 1 uvicorn worker, `uvloop`, `httptools`, backlog 1024, no access log, cores 0,1.
- Probe: separate process, cores 2,3, async client, warm keep-alive, barrier, `ARSENAL_LOAD_LIMITS>=B`, 1 conditioned profile `v1`, 2 bursts.
- Gate: server and client `request_first_chunk_ms` p95 <= 350 ms, 0 errors, RTF < 1.0.

## Step 1/4 — Ramp and window sweep

| B | Window (ms) | Server p95 (ms) | Client p95 (ms) | Queue p95 (ms) | Errors | RTF max | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 32 | 150 | 279.9 | 327.2 | 150.5 | 0 | 0.038 | PASS |
| 36 | 150 | 253.8 | 310.5 | 150.3 | 0 | 0.029 | PASS |
| 37 | 150 | 241.0 | 315.0 | 148.7 | 0 | 0.030 | PASS |
| 38 | 150 | 1802.3 | 1979.3 | 150.6 | 0 | 0.032 | FAIL |
| 48 | 5 (best) | 1088.6 | 1199.7 | 1365.9 | 0 | 0.037 | FAIL |
| 208 | 10 | 1789.4 | 6150.9 | 1863.7 | 2 | 0.021 | FAIL |
| 208 | 50 | 2177.7 | 6110.7 | 1897.2 | 1 | 0.020 | FAIL |
| 224 | 10 (best server) | 1542.1 | 5627.9 | 3692.7 | 0 | 0.028 | FAIL |
| 224 | 50 | 2364.0 | 6408.3 | 1961.1 | 2 | 0.028 | FAIL |

- B<=48 small windows (0–20 ms) split batches and increased tail.
- B<=37 passed with window 150 ms.
- B>=38 and B=224 failed in all tested windows.

## Step 2 — Server config

- `uvloop` + `httptools`, backlog 1024, no access log kept.
- A/B vs `asyncio` + `h11` was noisy on this host. No improvement claimed.

## Step 3 — Continuous batching

- No code. Plan required before code.
- Target: admit first-chunk jobs at chunk/frame boundaries. Reduce head-of-line wait.
- Needs dynamic KV/Mimi state admit/resize. Owner approval required.

## Outcomes

- Max B (server p95 <= 350): **37**.
- Max B (client p95 <= 350): **37**.
- Best window: **150 ms** for B<=37.
- B=224 gap: server +1192 ms vs 350 (best 1542.1 ms), client +5278 ms. Direct model 97.7 ms (FACT-0111).

## Follow-up

- Run load on a separate host for a fair client gate.
- Write Step 3 skeleton plan. Do not implement without approval.

