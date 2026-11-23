---
type: MAINTENANCE
time: 2026-11-23T17:10:00+05:30
summary: Continue the TRT sideline after a numeric parity blocker; push sideline branch before the fix.
paths: .stageset/runs/20261123-170329-RUN.md; patches/attention.patch
related: FACT-0171; 20261123-170329-RUN
commit: -
remote: -
branch: sideline/trt
---

# Session notes

## Decision

The owner approved further work on the sideline. The main repo stays clean.

## Work

- Keep all TRT work in branch `sideline/trt`.
- Push the branch before the next fix attempt.
- Next step: export smaller subgraphs and find the first op that diverges in
  ONNX Runtime.

## Follow-up

- Do not merge into main until numeric parity and speed gain are proved.
