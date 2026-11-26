---
id: IDEA-0011
title: Opt-in transliteration modes - sandbox complete
status: DISCOVERY
priority: P1
created_at: 2026-11-26T15:16:18+00:00
updated_at: 2026-11-26T15:16:18+00:00
created_in: .stageset/sessions/plan-transliteration-sandbox.md
updated_in: .stageset/sessions/plan-transliteration-sandbox.md
related_ideas: [IDEA-0009, IDEA-0010]
related_skeletons: []
---

# Opt-in transliteration modes - sandbox complete

## Summary

A separate sandbox built and verified opt-in transliteration modes. Base Arsenal
was not changed by this work. The sandbox is at
`/kaggle/working/arsenal_translit_sidecar/`.

## Problem

The base model speaks some Latin words with an English accent or mispronounces
Indian names such as `Pune`. Full transliteration of every word is not safe.
Manual word lists are not trusted.

## Goal

Provide three opt-in modes with no model call in the request path:

- `original`: current behavior.
- `indic-lite`: fixes observed failures and high-confidence names only.
- `indic`: applies the full transliteration map.

## Decisions

| Decision | Reason | Date | Event file |
| --- | --- | --- | --- |
| Keep sandbox outside `/kaggle/working/arsenal`. | Protect base model and gates. | 2026-11-26 | `.stageset/sessions/plan-transliteration-sandbox.md` |
| Use Aksharantar pairs as a static dictionary. | No runtime model call. | 2026-11-26 | `.stageset/sessions/plan-transliteration-sandbox.md` |
| Use CMUdict as a set, not pyspellchecker. | O(1) lookup and no slow correction step. | 2026-11-26 | `.stageset/sessions/plan-transliteration-sandbox.md` |
| Use observed-failure cache above CMUdict. | Fixes words that CMUdict knows but TTS still says badly. | 2026-11-26 | `.stageset/sessions/plan-transliteration-sandbox.md` |
| Keep default mode `original`. | Listening gate is still open. | 2026-11-26 | `.stageset/sessions/plan-transliteration-sandbox.md` |

## Runtime design

Protected spans are pre-normalized and held as placeholders:
URLs, emails, currency amounts, numbers, square footage, and all-caps acronyms.

Then the base normalizer runs. Then Latin tokens are looked up in order:

`indic-lite`: observed failure cache → lite map → CMUdict guard → offline fill with high confidence → original.

`indic`: observed failure cache → full map → offline fill → original.

All lookups are dict/set access. LRU cache is bounded.

## Built assets

- `full_hi.json.gz`: 4,400,241 bytes, 300,010 entries.
- `full_mr.json.gz`: 4,608,902 bytes, 300,009 entries.
- `lite_hi.json.gz` and `lite_mr.json.gz`: 273 bytes each.
- `english.json.gz`: 359,353 bytes, 126,052 words.
- `indicxlit_fill_hi.json.gz`: 1,113 bytes.
- `indicxlit_fill_mr.json.gz`: 1,270 bytes.

Source data:
- `ai4bharat/Aksharantar`, license CC0/CC-BY. Add attribution if shipped.
- `cmudict`, BSD/attribution requested.
- `Singla0009/all-indic-transliteration`, MIT. Used offline only.

## Verified facts

- `Pune → पुणे`, `Kharadi → खराडी`, `Sarvam → सर्वम`, `Tanvi → तनवी`.
- `indic-lite` keeps common English words in English.
- `indic` moves common English loanwords to Devanagari.
- Latency: original 0.693 ms/sentence, lite 0.917 ms/sentence, indic 0.922 ms/sentence.

## A/B WAVs

Nine WAVs are in `/kaggle/working/arsenal_translit_sidecar/out/`.
Names: `ab_realestate_*`, `ab_sarvam_*`, `ab_tanvi_*`.

## Not included

- No API field in base server.
- No changes to `Code/batch/server.py` for this feature.
- No base default change.
- No runtime IndicXlit model call.

## Open gate

Owner listening on the nine A/B WAVs. If accepted, create a Skeleton and SSLD for
main API integration. If rejected, keep the sandbox as evidence.

## Related files

- `/kaggle/working/arsenal_translit_sidecar/reports/FINAL_REPORT.md`
- `.stageset/runs/20261126-204618-RUN.md`
