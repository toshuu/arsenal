---
type: PROBE
time: 2026-11-26T08:48:20+00:00
summary: Generate Saurabh text WAVs with 3 s, 4 s, and full reference duration.
paths: /kaggle/working/saurabh_ref4_3s.wav; /kaggle/working/saurabh_ref4_4s.wav; /kaggle/working/saurabh_ref4_max.wav; /kaggle/working/hindi_cpu_texts.txt
related: 20261126-141820-RUN; FACT-0180
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use three text parts to reduce early EOS risk on CPU.
- Compare 3 s, 4 s, and full 7.344 s reference from the same source clip.

## Outcomes

- 3 s output: 11.00 s.
- 4 s output: 11.32 s.
- Full reference output: 11.64 s.

## Follow-up

- Owner listening comparison.
