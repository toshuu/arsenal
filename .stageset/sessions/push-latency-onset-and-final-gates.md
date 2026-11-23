---
type: PUSH
time: 2026-11-23T16:25:00+05:30
summary: Push latency onset fix, dual-GPU sweeps, and final conditioned gate table to origin/main as e499dc2.
paths: Code/batch/server.py; Skeletons/Code/batch/server.py; .stageset/facts.md
related: FACT-0168; FACT-0169; FACT-0170; 20261123-160927-RUN; 20261123-160927-RUN-02; 20261123-162117-RUN
commit: e499dc233c86a63064b9098385b8b5842cde7afa
remote: origin
branch: main
---

# Session notes

## Work

- Remote push succeeded from branch `main` to `origin`.
- Commit `e499dc2` contains the latency onset fix and all StageSet records for
  this session.

## Result

- Latency tier: first PCM frame sent raw, later frames still compressed.
- Sentence tier unchanged.
- Final conditioned gate table recorded in FACT-0170.
