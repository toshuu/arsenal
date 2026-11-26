---
type: PROBE
time: 2026-11-26T08:41:45+00:00
summary: Generate CPU WAVs with 3 s and 4 s slices of the new reference clip.
paths: /kaggle/working/hindi_english_ref4_3s.wav; /kaggle/working/hindi_english_ref4_4s.wav; /kaggle/working/hindi_cpu_texts.txt
related: IDEA-0009; 20261126-141145-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use the first 3 s and first 4 s of `/kaggle/working/multi-speaker (4).wav`.
- Keep the Hindi plus English text and normalization identical in both runs.

## Outcomes

- 3 s reference output: 9.28 s WAV.
- 4 s reference output: 12.16 s WAV.
- Both files are listed in `/kaggle/working/hindi_cpu_texts.txt`.

## Follow-up

- Owner listening comparison of the two reference durations.
