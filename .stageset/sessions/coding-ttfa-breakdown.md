---
type: CODING
time: 2026-11-15T23:55:00+05:30
summary: Profile TTFA/steady-frame breakdown (B=32,B=128 cond path) and document bottlenecks.
paths: Code/batch/batched_stream.py
related: IDEA-0003, SSLD-010, FACT-0033, FACT-0034, FACT-0035
commit: -
remote: -
branch: -
---

# Session notes

## Measurement (ad-hoc component profile, T4 FP16, cond profile 4.0s/cap16, compact)
- B=32: text prep 16.7 ms, state clone/init 2.9 ms, cond text into state 54.8 ms, flow step0 17.0 ms, mimi decode0 55.0 ms -> compute subtotal ~146.5 ms. Steady (avg 1-7): flow 16.5 + mimi 17.3 = 33.8 ms/frame.
- B=128: text prep 64.0 ms, state clone/init 8.3 ms, cond text into state 34.0 ms, flow step0 19.5 ms, mimi decode0 47.4 ms -> compute subtotal ~173.4 ms. Steady (avg 1-7): flow 18.9 + mimi 38.3 = 57.2 ms/frame.

## Bottlenecks
- TTFA compute: mimi decode0 + text conditioning dominant; text prep scales with B (CPU/tokenize+embed).
- TTFA tail to p95 (~225-350 ms at B=128): extra ~50-180 ms from lockstep batch tail (straggler/padding wait), batch formation/admission, host/callback overhead, content/length variance, runtime jitter. Not pure "mismanagement"; partly structural, reducible.
- Throughput/capacity: mimi decode dominates steady cost at high B (38 ms vs flow 19 ms at B=128). Flow relatively flat with B.

## Reduction levers (aligned SSLD-010)
- Pipelined/overlapped prep+compute, bucketing by length, continuous admission (reduce lockstep tail). T002-T005 path.
- Lower text-prep/conditioning cost, faster/smaller decode path, or grouped decode tuning where quality-safe.
