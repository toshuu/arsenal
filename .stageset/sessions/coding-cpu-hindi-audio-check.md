---
type: CODING
time: 2026-11-26T08:32:18+00:00
summary: Check CPU voice output, fix Hindi am/pm speech form, and regenerate two WAVs.
paths: Code/batch/text_normalize.py; Code/batch/normalize_tables.json; Code/tests/test_text_normalize.py; Ideas/IDEA-0009-text-normalization.md
related: IDEA-0009; FACT-0176; 20261126-140218-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use `शाम` and `सुबह` for Hindi am/pm. Use `सायं` and `सकाळी` for Marathi.
- Do not repeat an am/pm word already present before the time.
- Split long Hindi text into sentence parts for CPU generation. Join with
  120 ms silence. This avoids the early EOS omission.

## Outcomes

- `/kaggle/working/hindi_cpu_ref.wav` is 6.96 s and includes the final phrase.
- `/kaggle/working/hindi_english_cpu_ref.wav` is 12.24 s with the new am/pm form.
- `/kaggle/working/hindi_cpu_texts.txt` lists raw and normalized text.
- The pair file stays 78/78. The suite grows to 320 tests.

## Follow-up

- Real-audio listening gate on GPU is still open.
