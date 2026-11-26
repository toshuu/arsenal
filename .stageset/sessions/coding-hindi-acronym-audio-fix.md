---
type: CODING
time: 2026-11-26T08:38:18+00:00
summary: Fix Hindi OTP pronunciation with Devanagari acronym letters and regenerate the mixed WAV.
paths: Code/batch/text_normalize.py; Code/batch/normalize_tables.json; Code/tests/test_text_normalize.py; Ideas/IDEA-0009-text-normalization.md
related: IDEA-0009; FACT-0177; 20261126-140818-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use Devanagari acronym letters for Hindi and Marathi. Keep letter spacing for English.
- Correct `hi-otp-01` in the owner pair file to the Devanagari form.

## Outcomes

- `OTP` now normalizes to `ओ टी पी` in Hindi and Marathi.
- The mixed WAV is regenerated at `/kaggle/working/hindi_english_cpu_ref.wav`.
- The suite grows to 321 tests. The pair file stays 78/78.

## Follow-up

- Owner listening confirmation for the new OTP form.
