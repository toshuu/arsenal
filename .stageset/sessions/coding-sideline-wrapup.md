---
type: CODING
time: 2026-11-15T23:40:00+05:30
summary: Wrap sideline experiments (all blocked/no main gain), return to main path.
paths: Code/experiments/*; .stageset/facts.md
related: IDEA-0003, SSLD-010
commit: -
remote: -
branch: -
---

# Session notes

## Done
- INT8 (torchao, flow_lm): works, ear pass. TTFA lower, wall/RTF worse on T4 (FACT-0036). Capacity headroom only.
- INT4 (torchao 0.10, T4 sm75): all attempts failed (dtype/kernel/API issues) (FACT-0039). No run/sample.
- ONNX/ORT: dummy export/run only; full stateful flow/mimi blocked by ModelState dict + data-dependent cache guard. No end-to-end gain/sample (FACT-0037).
- TRT: libs absent in env, not attempted (FACT-0038).
- LiteRT: not in env; same stateful/export barriers.

## Decision
- Return to main PyTorch FP16 path (`Code/batch/`). No sideline merged into main. Main operating point unchanged (stable ~B=128, compact, 4.0s/cap16; B=160 unstable FACT-0033). SSLD-010 T005/T006 remain.
