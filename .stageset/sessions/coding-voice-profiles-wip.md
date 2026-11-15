---
type: CODING
time: 2026-11-15T20:40:00+05:30
summary: Formalize encoded voice profiles; revert unsafe conditioned-KV path; record B=128.
paths: Code/batch/batched_stream.py; Code/batch/VOICE_PROFILES.md; Ideas/optimization-strategy.md
related: IDEA-0003; FACT-0024; FACT-0025; FACT-0026; FACT-0027
commit: -
remote: -
branch: -
---

# Session notes

## Done

- Encoded voice profile save/load verified: temp 0 parity max abs diff 0.0 vs normal (4 texts). Profile skips WAV read/cut/encode.
- Attempted per-burst conditioned-KV reuse (text-only conditioning): TTFA/capacity probe looked good but temp 0 parity and batched text-padding correctness failed. Stream reverted to safe/parity-correct path.
- Sustained B=128 (T4 FP16, 4.0s/cap16, normal path, 5 bursts): p95 342.0–405.8 ms, 101–125/128 <350. User selected B=128 as current operating point (may increase).
- Docs: `Code/batch/VOICE_PROFILES.md`, Idea section 14, runs/facts updated.

## Next

- Implement correct conditioned-KV reuse with parity + batching tests to recover TTFA/capacity gains.
- Phase D waits for approval.
