---
type: CODING
time: 2026-11-20T01:33:15+05:30
summary: Ramp HTTP B and sweep windows (Steps 1,2,4). Find max passing B and 224 gap.
paths: Code/probes/probe_http_load.py; probes/out/sweep_b32_s14.json; probes/out/sweep_b36_s14.json; probes/out/sweep_b224_s4.json; probes/out/ramp_exact_s14.json
related: IDEA-0005; FACT-0110; FACT-0111; FACT-0112; FACT-0114; FACT-0115; FACT-0116
commit: -
remote: -
branch: -
---

# Session notes

## Setup

- Server: 1 uvicorn worker, `uvloop`, `httptools`, backlog 1024, no access log, cores 0,1 (`taskset`).
- Probe: separate process, cores 2,3, async client, warm keep-alive, barrier, `ARSENAL_LOAD_LIMITS>=B`, 1 conditioned profile `v1`, 2 bursts.
- Host: 1 T4, 4 vCPU (shared).

## Step 1/4 results (key)

| B | Window (ms) | Server p95 (ms) | Client p95 (ms) | Queue p95 (ms) | Errors | RTF max | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 32 | 150 | 279.9 | 327.2 | 150.5 | 0 | 0.038 | PASS |
| 36 | 150 | 253.8 | 310.5 | 150.3 | 0 | 0.029 | PASS |
| 37 | 150 | 241.0 | 315.0 | 148.7 | 0 | 0.030 | PASS |
| 38 | 150 | 1802.3 | 1979.3 | 150.6 | 0 | 0.032 | FAIL |
| 48 | 5 (best tried) | 1088.6 | 1199.7 | 1365.9 | 0 | 0.037 | FAIL |
| 224 | 10 (best server) | 1542.1 | 5627.9 | 3692.7 | 0 | 0.028 | FAIL |
| 224 | 50 | 2364.0 | 6408.3 | 1961.1 | 2 | 0.028 | FAIL |

Small windows (0–20) split B<=48 into multiple batches and increased tail. Window 150 passed B<=37 but caused tails at higher B.

## Step 2

- `uvloop`+`httptools` kept (standard). A/B with `asyncio`+`h11` was noisy/inconclusive on this host. No improvement claimed.

## Step 3

- No code. Plan needed: continuous batching at chunk/frame boundaries, first-chunk priority, KV/Mimi state admit/resize, compare gain to measured queue/head-of-line gap. Requires owner approval.

## Outcomes

- Max B (server p95 <= 350): **37**.
- Max B (client p95 <= 350): **37**.
- Best window: **150 ms** for B<=37.
- Gap to 224: large (server ~1542+ ms, client ~5628+ ms). Model compute 97.7 ms; limit is head-of-line/ingress and 4-vCPU host contention.

## Follow-up

- Separate load host for fair client gate.
- Step 3 skeleton plan after approval.
