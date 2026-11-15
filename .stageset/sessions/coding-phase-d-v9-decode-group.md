---
type: CODING
time: 2026-11-15T21:45:00+05:30
summary: Phase D start: add decode grouping (V9) to BatchedStream.
paths: Code/batch/batched_stream.py
related: IDEA-0003; FACT-0030
commit: -
remote: -
branch: -
---

# Session notes

## Done
- Added `decode_group` to `BatchedStream.stream` (buffer N latents, one `decode_from_latent`, split audio frames). Default 1.
- Temp 0 dg=2 vs dg=1: max diff ~8e-7. WAV `Code/probes/out/voice_profile_test/cond_dg2_t0.wav`.
- T4 FP16 conditioned profile B=128 5 bursts: dg=1 p95 343.1 ms 633/640 <350; dg=2 p95 365.4 ms 606/640 (TTFA hurt by grouped delivery), wall ~2.23s vs 2.33s.

## Open
- V8 CUDA graphs/compile spike (S5), V10 finished-row masking. Keep dg=1 default for TTFA.
