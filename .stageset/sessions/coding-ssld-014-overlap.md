---
type: CODING
time: 2026-11-16T13:40:00+05:30
summary: M2 overlap decode. Add a second CUDA stream helper and pipeline decode with the next flow step.
paths: Code/batch/overlap.py; Code/batch/batched_stream.py; Code/probes/check_overlap.py; Code/probes/probe_ttfa_stages.py; .stageset/facts.md; Ideas/optimization-strategy.md; Skeletons/Code/batch/overlap.py; LivingDocs/SSLD-014-overlap-decode.md
related: IDEA-0004; SSLD-014
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use one extra CUDA stream and one event. Do not use two full streams.
- Keep the synchronous path when `overlap_decode` is false.

## Outcomes

- T001: `Code/batch/overlap.py` imports and creates a second stream.

## Follow-up

- T002 to T005.
