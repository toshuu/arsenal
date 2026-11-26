---
type: CODING
time: 2026-11-26T07:46:12+00:00
summary: Apply all owner policy decisions and re-run the corrected pair file.
paths: Code/batch/text_normalize.py; Code/batch/normalize_tables.json; Code/tests/test_text_normalize.py; Code/probes/run_text_normalize_pairs.py; Code/requirements.txt; Code/deploy/modal_app.py
related: IDEA-0009; FACT-0175; 20261126-131612-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use Western scale for English non-INR money. Keep lakh and crore for INR and
  all Indic languages.
- Use `to` for ranges. Run phones, dates, times, and currency first.
- Handle `1/2`, `24/7`, and `3:1` as written. Leave other fractions unchanged.
- Read alphanumeric tokens by token type: letters-first and digits-first.
- Apply `minus` only at start, after space, or after `(`.
- Always emit `, ` after a comma between numbers.
- Use Hindi point word `दशमलव`.
- Use Hindi on-the-hour `पाँच बजे` and `बजकर ... मिनट`. Do not add a second
  `बजे`.
- Correct `hi-time-03` and `hi-mix-01` in the pair file. Remove `hi-mix-02`
  as a known limitation.

## Outcomes

- The corrected pair file passes 78/78. `must` is 46/46 and `policy` is 32/32.
- P1 to P8 pass. The suite grows to 319 tests.

## Follow-up

- Real-audio listening gate still waits for a GPU.
