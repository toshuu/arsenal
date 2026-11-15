---
type: IDEATION
time: 2026-11-15T18:35:00+05:30
summary: Add a per-GPU reproduction runbook for T4 and L4.
paths: Ideas/optimization-strategy.md
related: IDEA-0003; 20261115-182905-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep one result file per GPU. Never mix T4 and L4 numbers.
- Record `gpu_name` in every probe JSON.
- Repeat the same voice, texts, bursts, and temperature on L4.
- Use 3 bursts and random order for short runs.

## Outcomes

- Added section 13 to `Ideas/optimization-strategy.md`.

## Follow-up

- Run the same probe on L4 when it is available.
