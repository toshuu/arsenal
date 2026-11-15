---
type: CODING
time: 2026-11-15T14:45:00+05:00
summary: Formalize FP16 backbone path and run parity/TTFA check.
paths: Code/batch/fp16.py; Code/probes/check_batch_fp16.py; .stageset/runs/20261115-144500-RUN-fp16-formalize.md
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep backbone FP16, head/sampler FP32, Mimi decode FP32.
- Accept FP32-vs-FP16 parity corr 0.9975; flag FP16 batch-size drift corr 0.9469 for quality gate.

## Outcomes

- `Code/batch/fp16.py` and `Code/probes/check_batch_fp16.py` added.
- Check PASS with warning. B64 p95 280.3 ms, B80 p95 261.1 ms under 360 ms.
- FACT-0013 and run report added.

## Follow-up

- Run audio quality gate (listening/WER) for FP16 path.
- If pass, use FP16 as default for high-batch T4 runs and repeat on L4.
