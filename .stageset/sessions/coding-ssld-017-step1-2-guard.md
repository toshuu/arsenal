---
type: CODING
time: 2026-11-16T19:10:00+05:30
summary: Step1 memory safety (OOM+fit, limits), admission guard, KV scan note, voice cache prebuild script, Modal plan doc.
paths: Code/batch/batched_stream.py; Code/batch/build_voice_cache.py; LivingDocs/SSLD-017-modal-deployment-plan.md; Ideas/optimization-strategy.md; .stageset/facts.md; .stageset/runs/20261116-170000-RUN.md
related: SSLD-017; FACT-0079; FACT-0080; FACT-0081; FACT-0082; FACT-0083
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Set safe B=224 limit: max_frames <= 192 (15.36 s), keep >=1.5 GiB free.
- Add admission guard in BatchedStream.stream: raise ValueError when max_frames exceeds max_allowed_frames (env ARSENAL_MAX_FRAMES).
- Record KV scan behavior: complete_kv slices to valid prefix; no scan of full preallocated length.

## Outcomes

- OOM at B=224 max_frames=300 in init_states (Mimi KV prealloc). Fit ~+61 MB/frame.
- cProfile (B=224, 200 frames): attention/conv/linear dominate; emit_frame small.
- Modal plan written as LivingDocs/SSLD-017-modal-deployment-plan.md.
