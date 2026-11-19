---
type: MAINTENANCE
time: 2026-11-19T21:41:48+05:30
summary: Record the owner dislike point after the B224 under-120 ms baseline.
paths: Ideas/IDEA-0005-long-text-and-production-readiness.md; Skeletons/Probes/probe_http_load_224.md; .stageset/facts.md
related: IDEA-0005; FACT-0064; FACT-0087; FACT-0109
commit: d47025f
remote: -
branch: -
---

# Session notes

## Owner decision

- Dislike point: `2026-11-19T20:50:20+05:30`.
- Before it: B=224, p95 112.2 ms, max 118.6 ms, RTF 0.824. 30-burst p95 119.9 ms.
- After it: chunk scheduling, priority queue, larger windows, per-row voices, mixed-profile normal path. The owner dislikes these unless revalidated.
- Secondary checkpoint: `2026-11-19T20:11:00+05:30`, server default max batch 192.

## Outcomes

- IDEA-0005 has section 17.
- FACT-0109 records the decision.
- The READY 224-client skeleton points to the dislike point.

## Open items

- Next session must compare against the pre-dislike baseline before keeping or reverting recent work.
