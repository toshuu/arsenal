---
type: CODING
time: 2026-11-15T14:35:00+05:00
summary: Run S1 FP16 spike and measure B=64 p95 TTFA under 350 ms.
paths: .stageset/runs/20261115-143500-RUN-fp16-spike.md; Reports/burst-concurrency-2026-11-15.md; Ideas/optimization-strategy.md; .stageset/facts.md
related: IDEA-0003; SSLD-006
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep flow backbone FP16 and flow head/sampler FP32.
- Keep Mimi decode FP32 for stability.
- Treat this as a spike; quality gate is still required.

## Outcomes

- B=64: p95 233.2 ms, max 340.1 ms, 192/192 under 350 ms, RTF 0.008, VRAM 3313 MB.
- B=32-64 speedup: 1.16x-1.39x wall time at 32 frames.
- Parity vs FP32 B=1 at temp 0: max diff 0.036789, correlation 0.998183.
- FACT-0012 added. Report and strategy updated.

## Follow-up

- Run FP16 quality gate (listening/WER).
- If pass, formalize FP16 path and retest with shorter voice/capped first chunk.
