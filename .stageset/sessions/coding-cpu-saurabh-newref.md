---
type: CODING
time: 2026-11-26T09:03:09+00:00
summary: Revert Devanagari transliteration and regenerate with the new reference URL.
paths: /kaggle/working/new_ref.wav; /kaggle/working/saurabh_newref_3s.wav; /kaggle/working/saurabh_newref_4s.wav; /kaggle/working/saurabh_newref_max15s.wav; /kaggle/working/hindi_cpu_texts.txt
related: 20261126-143309-RUN; FACT-0183
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Revert to Latin English words in the Saurabh text.
- Use the new downloaded reference file.
- Use 15 s as the maximum stable reference length. 30 s stopped early.

## Outcomes

- 3 s output: 12.36 s.
- 4 s output: 12.52 s.
- 15 s output: 12.68 s.

## Follow-up

- Owner listening comparison.
