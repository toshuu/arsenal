---
type: IDEATION
time: 2026-11-26T14:25:46+00:00
summary: Document held chunk-context and max-token fixes without implementing them.
paths: Ideas/IDEA-0010-held-generation-path-fixes.md; Ideas/_index.md
related: IDEA-0009; IDEA-0010; 20261126-195546-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Hold the chunk-context continuity fix.
- Hold the `max_tokens=80` configuration change.
- Keep teacher forcing off.
- Keep the 4 s ref voice default, which is already in base.
- Activate a held fix only after a real failure or an owner request.

## Outcomes

- IDEA-0010 records findings, evidence, activation triggers, and verification plans.
- The Idea index links IDEA-0010.
- No implementation code was changed for these two fixes.

## Follow-up

- If word skipping returns, activate the chunk-context fix first.
- If a latency decision is needed, activate the max-token change with GPU gates.
