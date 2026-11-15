---
type: CODING
time: 2026-11-15T15:00:00+05:00
summary: Generate FP16 quality WAVs for manual listening check.
paths: Code/probes/out/fp16_quality/; .stageset/sessions/coding-fp16-quality-wavs.md
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Generate FP32 and FP16 B=1 samples, plus FP16 B=32 row 0, for manual quality check.
- Include English, Hindi, and Marathi sentences.

## Outcomes

- WAVs in `Code/probes/out/fp16_quality/` (gitignored, on disk): `fp32_b1_t0.wav`, `fp32_b1_t1.wav`, `fp16_b1_t0.wav`, `fp16_b1_t1.wav`, `fp16_b32_row0_t0.wav`, `fp32_hi.wav`, `fp16_hi.wav`, `fp32_mr.wav`, `fp16_mr.wav`.
- Manual quality gate is pending user listening.

## Follow-up

- Record quality gate result as PASS/FAIL in facts and run report.
- If pass, proceed with shorter voice and capped first chunk.
