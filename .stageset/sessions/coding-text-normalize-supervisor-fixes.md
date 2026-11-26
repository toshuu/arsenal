---
type: CODING
time: 2026-11-26T07:28:36+00:00
summary: Fix 5 supervisor-reported normalizer bugs and add regression tests.
paths: Code/batch/text_normalize.py; Code/batch/normalize_tables.json; Code/tests/test_text_normalize.py; Skeletons/Code/batch/text_normalize.py
related: IDEA-0009; FACT-0172; 20261126-125836-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Accept all 5 supervisor bugs after a local repro.
- Keep the Indian lakh and crore scale for English currency amounts. This is a
  known product choice, not a bug fix in this session.
- Add `oclock` and `oh` words to the JSON table so tuning stays data-only.
- Use a lowercase guard for bare domains. Do not expand `Okay.In` as a domain.

## Outcomes

- Sentence-final numbers, comma lists, Indian phone formats, on-the-hour times,
  minute<10 times, and capitalized multipliers now work.
- The test suite grows from 213 to 305 tests. All pass on CPU.
- The three fake-engine checks still return `{"ok": true}`.

## Follow-up

- Real-audio listening gate still waits for a GPU.
- A-09-01 is still unverified.
