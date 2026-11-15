---
type: CODING
time: 2026-11-15T21:50:00+05:30
summary: Phase D status - V9 done, V8/V10 assessed, B=128 under 350ms with conditioned profile.
paths: Code/batch/batched_stream.py; Ideas/optimization-strategy.md
related: IDEA-0003; FACT-0028; FACT-0029; FACT-0030
commit: 34ee00e
remote: origin/main
branch: main
---

# Session notes

## Current result
- **Current B under 350 ms:** **B=128** (T4, FP16, 4.0 s, cap 16, conditioned voice profile KV reuse, `decode_group=1`). Sustained 5 bursts: p95 281–331 ms, 128/128 <350 (FACT-0029). Recheck: p95 343.1 ms, 633/640 <350 (FACT-0030).
- **Normal path:** B=96 safe (p95 264–307 ms, 100% <350); B=128 372–400 ms, 94.4% (FACT-0028).

## Phase D (approved)
- **V9 done:** `decode_group` in `Code/batch/batched_stream.py` (default 1). dg=2: temp0 diff ~8e-7, wall -4%, TTFA worse (FACT-0030). Default kept 1.
- **V8/S5 assessed:** flow step ~21.7 ms/step at B=128. `torch.compile(reduce-overhead)` ~315 ms/step + cudagraph warnings. Manual CUDA graph spike pending.
- **V10 assessed:** frame lengths B=128 min 22/p50 28/p95 35/max 37; active after 22→127, 28→47. Full-batch state/decode blocks cheap masking. Needs active-set compaction/rebatch.

## Next (pending choice)
- V10 active-set compaction, V8 manual graph spike, re-measure for B>128. Phase E (L4) not started.
