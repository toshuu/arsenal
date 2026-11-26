<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/text_normalize.py
@stageset source_idea: IDEA-0009
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/coding-text-normalization.md
@stageset last_updated_in: .stageset/sessions/coding-text-normalization.md
@stageset implemented_in: .stageset/sessions/coding-text-normalization.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# text_normalize.py

## Purpose

Convert written text to spoken text before the TTS engine and the text chunker.
This is a CPU-only rule engine.

## Contract

- Input: `text: str`, `lang: str` in `{en, hi, mr, ta, te, kn, ml}`.
- Output: `str` with no written digits for the covered classes.
- Side effects: none. No GPU. No file writes at call time. The data table loads
  once and is cached.
- Unknown `lang` falls back to `en`.

## Structure

- `normalize(text, lang)` — public function. Applies the rules in the order
  below.
- `_tables()` — loads `normalize_tables.json` one time.
- `_lang_cfg(lang)` — returns the language data or the English data.
- `_num_words(number, lang)` — calls `indic_numtowords.num2words`.
- `_digit_words(digits, lang)` — reads each digit as one word.
- `_lang_for(text, start, end, default)` — picks the number language from the
  nearest script.
- `_currency_words(num, mult, code, lang)` — builds the spoken amount in the
  order number then currency word.
- Rule helpers for currency, dates, times, units, ordinals, phones, numbers,
  URLs, symbols, and acronyms.

## Pseudo-code

```text
normalize(text, lang):
    if text is empty: return ""
    if lang not supported: lang = "en"
    clean = NFC(text), remove zero-width, collapse space
    clean = replace_urls(clean)
    clean = replace_abbreviations(clean)
    clean = replace_currency(clean)   # prefix and suffix, before plain numbers
    clean = replace_dates(clean)
    clean = replace_times(clean)
    clean = replace_units(clean)
    clean = replace_ordinals(clean)
    clean = replace_phones(clean)     # 10+ digits, and OTP/PIN context
    clean = replace_numbers(clean)    # decimals first, then integers
    clean = replace_symbols(clean)
    clean = replace_acronyms(clean)
    clean = NFC(clean), fix punctuation space, collapse space
    return clean
```

Currency rule: match the symbol and the number as one unit. Return the number
words first, then the currency word. Example: `$20` becomes `twenty dollars`.
For `20.50`, use the major unit and the minor unit.

## Assumptions

ASSUMPTION: A-09-01 — The TTS tokenizer accepts native-script number words. [UNVERIFIED on real audio]

ASSUMPTION: A-09-02 — `indic_numtowords.num2words` is installed in the image. [CONFIRMED by FACT-0171]

## Edge cases

- Empty text returns an empty string.
- A symbol-only text can become empty. The HTTP layer returns 422.
- An invalid date (day over 31 or month over 12) stays as written.
- An invalid time (hour over 23 or minute over 59) stays as written.
- A number over 1,000,000 uses the Indian lakh and crore scale.
- A Devanagari span uses `hi` or `mr` from the request. It does not guess.

## Checks

### CHECK-TEXT-NORM-01 — Unit tests pass on CPU

- Command: `python -m pytest Code/tests/test_text_normalize.py -q`
- Predicted output: `311 passed`
- Pass condition: exit code 0 and all tests pass.
- Fail condition: any failed test or non-zero exit code.

### CHECK-TEXT-NORM-02 — Server fake-engine checks do not regress

- Command: `python Code/probes/check_server_modes.py`
- Predicted output: `{"ok": true}`
- Pass condition: the result is true.
- Fail condition: any other result.

### CHECK-TEXT-NORM-03 — Call WebSocket fake-engine checks do not regress

- Command: `python Code/probes/check_call_ws.py`
- Predicted output: `{"ok": true}`
- Pass condition: the result is true.
- Fail condition: any other result.

### CHECK-TEXT-NORM-04 — Server fake-engine checks do not regress

- Command: `python Code/probes/check_server.py`
- Predicted output: `{"ok": true}`
- Pass condition: the result is true.
- Fail condition: any other result.

## References

- `Ideas/IDEA-0009-text-normalization.md`
- `Code/batch/text_normalize.py`
- `Code/batch/normalize_tables.json`
- `Code/tests/test_text_normalize.py`
- `.stageset/runs/20261126-124922-RUN.md`