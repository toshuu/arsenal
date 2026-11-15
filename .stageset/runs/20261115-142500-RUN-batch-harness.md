# Run report: Phase B batched burst harness

Run ID: 20261115-142500-RUN-batch-harness
Type: BURST probe (SSLD-006, check T002-T005)
Command: python Code/probes/bench_batch_server.py --bs 30,32,34,35,36 --bursts 5 --parity-b 32 --out Code/probes/out/bench_batch_server_knee.json
Output: Code/probes/out/bench_batch_server_knee.json

## Observed facts

| Batch | p50 ms | p95 ms | max ms | under 350 ms | wall s | RTF | VRAM MB |
|---|---|---|---|---|---|---|---|
| 30 | 222.4 | 278.8 | 375.8 | 149/150 | 2.42 | 0.013 | 2137 |
| 32 | 260.1 | 327.0 | 404.8 | 156/160 | 2.56 | 0.013 | 2247 |
| 34 | 280.0 | 359.7 | 398.0 | 160/170 | 2.81 | 0.013 | 2360 |
| 35 | 285.8 | 358.5 | 438.4 | 165/175 | 2.88 | 0.013 | 2416 |
| 36 | 290.8 | 357.6 | 432.1 | 168/180 | 2.94 | 0.013 | 2476 |

Parity B=32 vs B=1 (temp 0, 32 frames): max abs diff 1.07e-04, correlation 1.0.

## Check results

T002 harness run: OK, prints BENCH_BATCH_SERVER_DONE.
T003 parity maxdiff < 1e-3: True.
T004 B=32 p95 < 350 and under-350 fraction >= 0.95: True.
T005 B=30 p95 < 350: True.

## Notes

- TTFA at high batch is dominated by leading silent codec frames, not by compute.
- B=34 p95 ranged 295.0 ms (earlier run) to 359.7 ms (this run). It is unstable.
- B=35 and B=36 fail p95. B=32 passes p95 but has a tail above 350 ms.
- Recommend B=30 as the production-safe point; B=32 is the measured p95 ceiling.
