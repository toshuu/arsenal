---
type: CODING
time: 2026-11-26T07:19:25+00:00
summary: Add CPU text normalization before the TTS chunker and wire it to HTTP and WebSocket.
paths: Code/batch/text_normalize.py; Code/batch/normalize_tables.json; Code/tests/test_text_normalize.py; Code/batch/server.py; Ideas/IDEA-0009-text-normalization.md; Skeletons/Code/batch/text_normalize.py
related: IDEA-0009; 20261126-124922-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use `indic-numtowords` for numbers in all 7 languages.
- Use regex rules and one JSON table per language. Do not use a model.
- Normalize before `_text_chunks` and `split_call_text`.
- Add `lang` to the HTTP and WebSocket payloads. Default is `ARSENAL_TEXT_LANG`
  or `en`.
- Do not use `whisper-normalizer` for Indic output.

## Outcomes

- `Code/batch/text_normalize.py` and `Code/batch/normalize_tables.json` exist.
- 213 CPU tests pass.
- The server modes, call WebSocket, and server fake-engine checks pass.
- `Code/batch/server.py` normalizes text in `/tts`, `/tts/stream`,
  `/tts/batch`, and `/ws/tts`.

## Follow-up

- Run a real-audio listening gate when a GPU is available.
- Add per-language words for `dot` and `slash` if listening shows a bad mix.
