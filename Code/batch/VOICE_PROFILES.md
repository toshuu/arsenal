# Voice profiles (WIP)

## Purpose

Use one voice in two ways:
1. **Normal path (default):** give a voice WAV. The stream encodes the voice once at init and uses it for bursts. Use `voice_seconds=4.0` as the default operating point on T4.
2. **Conditioned profile (opt-in):** compute the voice conditioning once, save it, and reuse it. Each burst restores the conditioned KV state and runs text only. This removes the per-burst voice-prompt step and lowers TTFA.

Both modes stay available. No profile = normal path.

## Normal path (4.0 s default)

```python
from batch.batched_stream import BatchedStream

stream = BatchedStream(
    model,
    voice="path/to/voice.wav",
    voice_seconds=4.0,      # default operating point
    max_first_tokens=16,    # optional TTFA lever (truncates first chunk text)
)
audio = stream.stream(texts, on_chunk=callback)
```

## Create a conditioned profile (once)

```python
from batch.batched_stream import BatchedStream

# Build from a voice WAV (same cut/order as normal path).
stream = BatchedStream(model, voice="path/to/voice.wav", voice_seconds=4.0)
stream.save_voice_profile("profiles/my_voice.pt", conditioned=True)
```

`conditioned=True` saves encoded voice data and the voice-conditioned flow-LM KV state.

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

`voice_seconds` comes from the profile. You can keep many pre-made profiles and select by request.

## Measured (T4, FP16, voice 4.0 s, cap 16, unique text, streaming)

- TTFA B=96 (5 bursts): profile p95 avg 232.8 ms (96/96 <350) vs normal 300.9 ms. (FACT-0024, run `20261115-202240-RUN`)
- Capacity with profile (3 rounds): B=128 p95 277 ms, 383/384 <350 (99.7%); B=144 p95 307 ms, 95.8% <350. (FACT-0025)

## Status and caveats

- WIP implementation in `Code/batch/batched_stream.py` (commit `cb7cd55`).
- Temp=0 waveform parity vs normal path is not confirmed.
- `max_first_tokens` truncates the first text chunk; stream later chunks in production.
- Opt-in: do not pass `voice_profile` to keep the normal 4.0 s path.
