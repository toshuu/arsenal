---
type: CODING
time: 2026-11-26T14:22:51+00:00
summary: Add square-footage normalization to the base normalizer.
paths: Code/batch/text_normalize.py; Code/batch/normalize_tables.json; Code/tests/test_text_normalize.py
related: IDEA-0009; 20261126-195251-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Map `sq. ft.`, `sq ft`, `square feet`, and `square foot` to a per-language unit word.
- Keep the number in English when `lang=en`.
- Use `स्क्वायर फीट` for Hindi and Marathi.

## Outcomes

- `2,000 sq. ft.` gives `two thousand स्क्वायर फीट` for `en`.
- `2,000 square feet` gives `दो हज़ार स्क्वायर फीट` for `hi`.
- The suite grows to 322 tests. Pair file stays 78/78.

## Follow-up

- Add more Indian real-estate terms through a StageSet idea if needed.
