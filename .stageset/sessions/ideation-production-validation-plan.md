---
type: IDEATION
time: 2026-11-19T20:20:00+05:30
summary: Plan four production-validation tasks before L4 and Modal. Update IDEA-0005 findings.
paths: Ideas/IDEA-0005-long-text-and-production-readiness.md; Ideas/_index.md
related: IDEA-0005; FACT-0088; FACT-0089; FACT-0090; FACT-0091; FACT-0095; FACT-0096; FACT-0097
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Finding A is VERIFIED. Finding B and E are PARTLY VERIFIED. Findings C and D are PLANNED.
- Do four tasks before L4 and Modal:
  1. End-to-end HTTP load probe.
  2. Long text through HTTP with a profile.
  3. Chunk join and carried-state decision.
  4. Slow-client stream backpressure.
- Do not add a true mixed-profile GPU batch or a true conditioned mixed-length call in this round.
- Add IDEA-0005 to the ideas index.

## Outcomes

- IDEA-0005 has a current status table and a task plan with pass conditions.
- The plan uses the new measured figures: B=224, p95 112.2 ms; stream TTFB 82.9 ms.
- StageSet validate passes.

## Open items

- Implement planned work 1 to 4.
