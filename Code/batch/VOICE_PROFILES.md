# Voice profiles

## Purpose

Use one voice in two ways:
1. **Normal path (default):** give a voice WAV. Encodes voice once at init; normal per-burst conditioning. Default `voice_seconds=4.0`.
2. **Conditioned profile (opt-in, faster TTFA):** save voice-conditioned KV state once and reuse it. Each burst restores state and conditions text only (no per-burst voice prompt). Use when first-chunk text token lengths match in the batch (uniform with `max_first_tokens`).

Both modes available. No profile = normal path.

## Normal path (4.0 s default)

```python
from batch.batched_stream import BatchedStream

stream = BatchedStream(
    model,
    voice="path/to/voice.wav",
    voice_seconds=4.0,
    max_first_tokens=16,    # optional TTFA lever
)
audio = stream.stream(texts, on_chunk=callback)
```

## Create a conditioned profile (once)

```python
from batch.batched_stream import BatchedStream

stream = BatchedStream(model, voice="path/to/voice.wav", voice_seconds=4.0)
stream.save_voice_profile("profiles/my_voice.pt", conditioned=True)
```

`conditioned=True` saves encoded voice + voice-conditioned flow-LM KV state (KV-reuse fast path).

## Use a conditioned profile

```python
from batch.batched_stream import BatchedStream

stream = BatchedStream(
    model,
    voice_profile="profiles/my_voice.pt",
    max_first_tokens=16,
)
audio = stream.stream(texts, on_chunk=callback)
```

`voice_seconds` comes from profile. Keep many pre-made profiles and select by request.

## Selected operating point (user)

- T4, FP16, 4.0 s, cap 16, **B=128** target (may increase). With conditioned profile KV reuse: B=128 p95 281–331 ms, 128/128 <350 ms (5 bursts, FACT-0029). Normal path B=128: 372–400 ms 94.4% (FACT-0028).

## Server: default clip, opt-in profile

The server uses the **reference voice clip** by default (normal path). To use a
precomputed profile, send `voice_profile` in the payload:

```json
{"text": "Hello.", "voice_profile": "alba"}
```

The server reads profiles from `ARSENAL_VOICE_PROFILES`:

```bash
ARSENAL_VOICE_PROFILES="alba=/app/profiles/alba.pt;casual=/app/profiles/casual.pt"
```

An unknown id returns 400. A batch request with a profile must have equal
first-chunk token lengths across its texts, else it returns 422. The worker
groups jobs by profile id and first-chunk token length, so one batch never
mixes conditioned states.

Build the profile files at image time:

```bash
python Code/batch/build_voice_profiles.py /app/profiles \
    alba=voices/alba.wav casual=voices/casual.wav
```

This is separate from the voice-embedding cache (`build_voice_cache.py`). The
cache saves the 650 ms voice encode at boot. A conditioned profile also saves
the per-burst voice conditioning, so it is the TTFA lever.

## First-chunk token length (why a batch can fail)

The conditioned KV state has one fixed prefix. Each row then adds its text
tokens. Rows with different token counts have different KV positions. Bad audio
can result.

Example:
- `"Hi."` gives 2 tokens.
- `"Please read this sentence."` gives 5 tokens.

These two texts in one conditioned batch differ. The server groups them into
separate calls, so this is safe. A 422 returns only if a single profile request
has mixed lengths.

Safe options: group by token count (the server does this), pad with a correct
mask and per-row positions (needs model changes and audio tests), or run one
text per call.

The full guide is `docs/voice-profiles.md`.

## Common mistakes

- Save with `conditioned=True`. Without it, profile has no `voice_state`; stream runs normal path (no TTFA gain).
- Load with `voice_profile=...` (opt-in). Passing `voice=` uses normal path.
- Keep first-chunk text token lengths uniform for batched KV reuse. Set `max_first_tokens` (e.g. 16). Mixed lengths in one batch can produce bad/long audio (silence, overrun). If lengths differ, stream one request at a time.
- Do not compare KV-reuse output bit-for-bit to normal path. Conditioning differs; validate by ear and TTFA, not waveform equality.
- Do not use KV-reuse for quality checks without `max_first_tokens` awareness: `max_first_tokens` truncates the first chunk (used in TTFA tests). For full-text ear check, stream per request or use a cap that covers the text.

## Notes

- Long-term guide: `docs/voice-profiles.md`.
- Impl: `Code/batch/batched_stream.py`.
- `max_first_tokens` truncates first text chunk; stream later chunks in production.
