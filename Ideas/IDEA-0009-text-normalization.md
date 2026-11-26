---
id: IDEA-0009
title: Rule-based text normalization before TTS
status: IMPLEMENTED
priority: P0
created_at: 2026-11-26T07:19:25+00:00
updated_at: 2026-11-26T07:19:25+00:00
created_in: .stageset/sessions/coding-text-normalization.md
updated_in: .stageset/sessions/coding-text-normalization.md
related_ideas: [IDEA-0008]
related_skeletons: [Skeletons/Code/batch/text_normalize.py]
---

# Rule-based text normalization before TTS

## Summary

Add a CPU-only normalizer. It converts written forms into spoken forms before
the text reaches the TTS engine and the text chunker. It uses regex rules and
per-language data tables. It does not use a model and does not use a GPU.

## Problem

The TTS model reads written text as is. It reads `Rs. 1,502` wrong. It reads
currency symbols, decimals, dates, times, phone numbers, units, and
abbreviations wrong. It can also split a number at a comma and make a pause.

## Goal

Return clean spoken text for `en`, `hi`, `mr`, `ta`, `te`, `kn`, and `ml`.
The operation must be fast on CPU and must run in the request path.

## Scope

### Included

- Currency prefix and suffix forms, with singular and plural words.
- Lakh, crore, k, M, and billion multipliers.
- Decimals, ordinals, dates, times, and phone numbers.
- Units and percent.
- Abbreviations (`Dr.`, `Mr.`, `No.`).
- Symbols, acronyms, URLs, and emails.
- Code-mixed number language selection from the nearest script.
- Data tables in one JSON file for easy tuning.

### Not included

- Retraining the TTS model.
- Punctuation changes for prosody.
- Translation of text. The model already handles code-mixed speech.
- GPU tests. The normalizer is CPU only.

## Requirements

- `normalize(text, lang)` must return a string with no written digits for the
  covered classes.
- The function must not use a GPU.
- The function must be deterministic.
- The function must run before `_text_chunks` and `split_call_text`.
- The API must accept a `lang` field for HTTP and WebSocket requests.
- The default language must come from `ARSENAL_TEXT_LANG` and must be `en`.

## Decisions

| Decision | Reason | Date | Event file |
| --- | --- | --- | --- |
| Use `indic-numtowords` as the number engine. | It covers all 7 model languages and returns native script. | 2026-11-26 | `.stageset/sessions/coding-text-normalization.md` |
| Keep rules and per-language data in the repository. | No heavy WFST dependency and no build step. | 2026-11-26 | `.stageset/sessions/coding-text-normalization.md` |
| Normalize before chunking. | Protect `Rs. 1,502` and `Dr.` from a bad split. | 2026-11-26 | `.stageset/sessions/coding-text-normalization.md` |
| Do not use `whisper-normalizer` for Indic output. | Its Indic TTS mode left English words and broke ordinals, dates, and commas in a test. | 2026-11-26 | `.stageset/runs/20261126-124922-RUN.md` |
| Apply all 23 owner policy decisions to the pair file. | Owner approved each written result. | 2026-11-26 | `.stageset/sessions/coding-text-normalize-policy-decisions.md` |
| Owner accepted normalization quality. | Pair file passes 78/78. | 2026-11-26 | `.stageset/sessions/coding-text-normalize-policy-decisions.md` |
| Use am/pm words instead of letter names for Hindi and Marathi. | The model spoke `p m` as letters. | 2026-11-26 | `.stageset/sessions/coding-cpu-hindi-audio-check.md` |
| Use Devanagari acronym letters for Hindi and Marathi. | `O T P` sounded like `O-bhi` on CPU audio. | 2026-11-26 | `.stageset/sessions/coding-hindi-acronym-audio-fix.md` |
| Add square-footage rule. | `sq. ft.` was spoken badly in a real-estate call sample. | 2026-11-26 | `.stageset/sessions/coding-text-normalize-sqft.md` |

## Facts

- `indic-numtowords` 1.1.0 returns clean native-script words for all 7
  languages. See `.stageset/runs/20261126-124922-RUN.md`.
- The normalizer test suite passes on CPU. See FACT-0171.

## Assumptions

- ASSUMPTION: A-09-01 — The TTS tokenizer accepts native-script number words. [UNVERIFIED on real audio, no GPU today]

## Open questions

- None for the CPU normalizer.
- The owner listening gate on real audio is open until a GPU is available.

## Risks and edge cases

- A date like `12/03/2025` uses the day-month-year order. This is the Indian
  convention. A user that sends month-day-year text gets the day and month
  swapped.
- English numbers use the Indian lakh and crore scale from
  `indic-numtowords`.
- Marathi and Hindi share the Devanagari script. A code-mixed span uses the
  request language when the default is `hi` or `mr`.
- A bare number with no nearby letters uses the request language.

## Acceptance criteria

- `python -m pytest Code/tests/test_text_normalize.py -q` passes.
- `python Code/probes/check_server_modes.py` returns `{"ok": true}`.
- `python Code/probes/check_call_ws.py` returns `{"ok": true}`.
- `python Code/probes/check_server.py` returns `{"ok": true}`.

## Related files

- `Code/batch/text_normalize.py`
- `Code/batch/normalize_tables.json`
- `Code/tests/test_text_normalize.py`
- `Code/batch/server.py`
- `Skeletons/Code/batch/text_normalize.py`
