# Voice profiles (WIP)

## Purpose

Use one voice in two ways:
1. **Normal path (default):** give a voice WAV. The stream encodes the voice once at init and uses it for bursts. Use `voice_seconds=4.0` as the default operating point on T4.
2. **Voice profile (opt-in):** compute the encoded voice prompt once, save it, and load it later. This skips WAV read/cut/encode on startup. The normal batched conditioning path still runs per burst.

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

## Create a profile (once)

```python
from batch.batched_stream import BatchedStream

stream = BatchedStream(model, voice="path/to/voice.wav", voice_seconds=4.0)
stream.save_voice_profile("profiles/my_voice.pt")
```

## Use a profile

```python
from batch.batched_stream import BatchedStream

stream = BatchedStream(
    model,
    voice_profile="profiles/my_voice.pt",
    max_first_tokens=16,
)
audio = stream.stream(texts, on_chunk=callback)
```

`voice_seconds` comes from the profile. Keep many pre-made profiles and select by request.

## Selected operating point (current)

- T4, FP16, streaming, unique text, voice 4.0 s, cap 16, **B=128 selected** (user). May increase with further efficiency work.

## Measured

- Encoded profile parity (temp 0, FP16, 4 texts, cap 16): max abs diff 0.0 vs normal, same lengths. (FACT-0026, run `20261115-203726-RUN`)
- Sustained normal-path check, T4 FP16, 4.0 s/cap 16, B=128, 5 bursts: p95 342.0–405.8 ms, under-350 101–125/128. (FACT-0027, run `20261115-203726-RUN`)
- Earlier conditioned-KV reuse probe showed TTFA/capacity gains but waveform parity was not confirmed and batched text-padding correctness failed; stream reverted to safe path. (FACT-0024/0025 marked exploratory)

## Caveats

- `Code/batch/batched_stream.py` is WIP.
- `max_first_tokens` truncates the first text chunk; stream later chunks in production.
- Profile now stores/reuses encoded voice prompt. Per-burst conditioned-KV reuse is future work.
