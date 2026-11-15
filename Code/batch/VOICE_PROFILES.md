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

## Notes

- Impl: `Code/batch/batched_stream.py` (KV-reuse path when `voice_state` present and uniform text lengths; else normal path).
- KV-reuse path is a different conditioning procedure than normal; not bit-identical, quality checked by ear in probes.
- `max_first_tokens` truncates first text chunk; stream later chunks in production.
