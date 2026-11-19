---
type: MAINTENANCE
time: 2026-11-20T00:45:32+05:30
summary: Record current standing: B and time, reverted regressions, delusion, and next steps.
paths: .stageset/facts.md
related: IDEA-0005; FACT-0109; FACT-0110; FACT-0111; FACT-0112; FACT-0113; FACT-0114
commit: -
remote: -
branch: -
---

# Status snapshot (2026-11-20T00:45:32+05:30)

## Standing

| Gate | B | First-chunk p95 | Result | Evidence |
| --- | ---: | ---: | --- | --- |
| Direct model (conditioned, in-process) | 224 rows | 97.7 ms | PASS | FACT-0111 |
| HTTP, 32 clients | 32 | 340.6 ms client, 294.0 ms server | PASS | FACT-0110 |
| HTTP, 224 clients (single profile) | 224 | 7379 ms client, 3166 ms server (window 700); best server 1145 ms (window 50) | FAIL | FACT-0112 |

RTF < 1.0 in all HTTP runs. No model errors.

## Bad deeds and delusion

- **Delusion (partial):** 112 ms was direct in-process. 6–13 s was HTTP with 224 sockets and a queue. The runs were not equal.
- **Bad deeds (real, reverted):** Probe lost `ARSENAL_LOAD_LIMITS` and `httpx.Limits`. `_group_key` returned `None`. `ARSENAL_BATCH_TARGET` default was 32. Per-row voice prefill made 224 conditioner calls. `chunks_for` blocked the event loop. Fixed in `fcd4253` (FACT-0113).
- **Not bad:** Model compute did not regress (97.7 ms < 112.2 ms). B=224 memory and RTF are valid.

## Next

1. Keep gates: direct B=224 and 32-client HTTP.
2. Plan continuous batching in a new skeleton (admit rows mid-generation). Target: head-of-line blocking. High risk.
3. Run the load generator on a separate host. Gate on server `request_first_chunk_ms`.
4. Compare only equal runs. Record env and evidence.
