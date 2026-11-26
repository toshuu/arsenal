---
type: CODING
time: 2026-11-26T08:44:20+00:00
summary: Fix the 3 s reference CPU WAV that cut off in the middle of OTP.
paths: /kaggle/working/hindi_english_ref4_3s.wav; /kaggle/working/hindi_cpu_texts.txt
related: 20261126-141420-RUN; FACT-0179
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep the 4 s reference WAV unchanged.
- Regenerate only the 3 s reference WAV with three text parts.

## Outcomes

- 3 s output is 12.28 s and includes the full OTP phrase.
- The text file records the three parts.

## Follow-up

- Owner listening confirmation.
