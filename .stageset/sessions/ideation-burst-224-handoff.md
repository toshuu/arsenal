---
type: IDEATION
time: 2026-11-19T21:39:00+05:30
summary: Handoff for the failed 224-client burst gate. Record traps, evidence, and a READY skeleton.
paths: Ideas/IDEA-0005-long-text-and-production-readiness.md; Skeletons/Probes/probe_http_load_224.md
related: IDEA-0005; FACT-0107; FACT-0108
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- The 224-client burst gate is not fixed. It is a P0 handoff item.
- Keep FACT-0108 as a negative fact.
- The 32-client gate passes with target-driven batching.
- Probe client limits must stay fixed per comparison.
- Do not use the all-chunk first metric as the TTFA gate.

## Outcomes

- IDEA-0005 has section 16 with current state, traps, next work, key files, and non-goals.
- A READY skeleton exists for the next session.

## Open items

- Add per-request first-chunk metrics.
- Fix the 224-client gate.
- Owner listening gate for chunk joins.
