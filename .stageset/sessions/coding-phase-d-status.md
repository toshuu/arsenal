---
type: CODING
time: 2026-11-15T21:50:00+05:30
summary: Phase D status - V9 done, V8/V10 assessed, B=128 under 350ms with conditioned profile.
paths: Code/batch/batched_stream.py; Ideas/optimization-strategy.md
related: IDEA-0003; FACT-0028; FACT-0029; FACT-0030
commit: -
remote: -
branch: main
---

# Session notes

## Current result
- **Current B under 350 ms:** **B=160** with `compact=True` (T4, FP16, 4.0 s, cap 16, conditioned voice profile KV reuse, `decode_group=1`). 5 bursts: B=128 p95 272.7 ms 636/640, B=144 p95 300.5 ms 700/720, B=160 p95 337.7 ms 800/800 (FACT-0031). Previous (no compaction): B=128 p95 281–343 ms (FACT-0029/0030).
- **Normal path:** B=96 safe (FACT-0028).

## Phase D (approved)
- **V9 done:** `decode_group` added, default 1 (FACT-0030).
- **V10 done:** active-set compaction, default True (FACT-0031). Major TTFA/capacity gain.
- **V8/S5 spike done:** torch.compile no gain (14.68–15.73 vs 14.05 ms/step baseline, B=128). Manual CUDA graph not implemented (dynamic state/compaction) (FACT-0032).

## Gate D soak (FACT-0033)
- B=160, 475 sequential bursts (160 parallel/burst), 76,000 req, ~23 min, 0 errors/OOM.
- TTFA: 97.52% <350 ms; burst p95 median 275.8 ms, p95-of-p95 416.6 ms, 64/475 bursts >350. **Not stable.**
- RTF: median 0.0015 (pass).

## Next
- Stable B for <350 ms ~128-144 (sustained). Phase E (L4) or further margin work on approval.
