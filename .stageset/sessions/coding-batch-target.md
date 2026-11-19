---
type: CODING
time: 2026-11-19T21:32:00+05:30
summary: Add target-driven batching. Set window to 300 ms with target 32. Recheck B224 with 40 ms.
paths: Code/batch/server.py; Code/probes/probe_http_load.py; docs/voice-profiles.md; Code/batch/VOICE_PROFILES.md; Ideas/IDEA-0005-long-text-and-production-readiness.md; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0107; FACT-0108
commit: 284618c
remote: -
branch: -
---

# Session notes

## Decisions

- Wait for 32 jobs or a 300 ms cap. Start early when 32 jobs arrive.
- Keep first-chunk priority.
- Keep the B=224 40 ms failure as a negative fact.

## Outcomes

- Three 32-client runs pass. Client p95 205.76, 289.30, 191.96 ms.
- B=224 with 40 ms fails. Client p95 13574.29 ms.
- Standard probes pass.

## Open items

- 224-client bursts need a different admission rule.
