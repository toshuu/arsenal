---
type: IDEATION
time: 2026-11-26T15:16:18+00:00
summary: Build and verify opt-in transliteration modes in a separate sandbox.
paths: /kaggle/working/arsenal_translit_sidecar; Ideas/IDEA-0011-transliteration-modes-sandbox.md
related: IDEA-0009; IDEA-0010; IDEA-0011; 20261126-204618-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep the sandbox outside the base Arsenal folder.
- Use `original`, `indic-lite`, and `indic` modes.
- Keep `original` as the default.
- Build static maps offline. Do not call IndicXlit at runtime.
- Use CMUdict as a set. Do not use pyspellchecker.
- Put observed failures above CMUdict.

## Outcomes

- Aksharantar and CMUdict maps built for Hindi and Marathi.
- Runtime wrapper verified with latency under 1 ms per sentence.
- Nine A/B WAVs generated in the sandbox.
- Base tests pass: 322 tests, 78/78 pair file, fake-engine checks.

## Follow-up

- Owner listens to the nine A/B WAVs.
- If accepted, create a Skeleton and SSLD for main API integration.
