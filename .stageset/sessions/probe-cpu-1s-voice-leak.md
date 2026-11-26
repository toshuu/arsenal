---
type: PROBE
time: 2026-11-26T09:20:52+00:00
summary: Identify the high-quality first second in the 1 s reference variant.
paths: /kaggle/working/saurabh_ms7_v2_1s.wav; /kaggle/working/multi-speaker (7).wav
related: 20261126-145052-RUN; FACT-0187
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Treat the high-quality first second as a reference-leak artifact, not a separate voice.

## Outcomes

- Correlation with the reference first second is +0.383 at zero lag.
- Other variants and the default voice show near-zero correlation.

## Follow-up

- Decide whether to exploit prompt continuation deliberately.
