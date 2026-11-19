# Voice profiles: build and use

This file is the long-term guide. Read it when you add voices or wire the image.

## What a voice profile is

A voice profile is a `.pt` file. It holds:
- the encoded voice tensor, and
- the voice-conditioned flow-LM KV state.

The stream restores that state and conditions only the text. This skips voice
conditioning on each burst. That is the TTFA gain.

Do not confuse it with the voice cache:
- Voice cache: saves only the voice encode at boot (about 0.65 s).
- Voice profile: saves the per-burst voice conditioning.

## Build one profile

```bash
python Code/batch/build_voice_profiles.py /app/profiles \
    alba=voices/alba.wav
```

Output: `PROFILE alba /app/profiles/alba.pt`.

## Build many profiles

One model load builds all files:

```bash
python Code/batch/build_voice_profiles.py /app/profiles \
    v1=voices/v1.wav \
    v2=voices/v2.wav \
    v44=voices/v44.wav
```

Each profile is about 1.4 MB. Model weights are shared at run time.

## Start the server

```bash
ARSENAL_POCKET_TTS=/path/to/pocket-tts \
ARSENAL_VOICE_PROFILES="alba=/app/profiles/alba.pt;v44=/app/profiles/v44.pt" \
python -m uvicorn batch.server:app --app-dir Code
```

Use a semicolon or a comma between entries.

## Use a profile

```bash
curl -s -X POST http://127.0.0.1:8000/tts \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello.","voice_profile":"v44"}' -o out.wav
```

No `voice_profile` field: the server uses the reference voice clip on the
normal path. An unknown id returns 400.

## Many voices in live traffic

You can supply 50 profiles and select any of them per request. One HTTP batch
can contain jobs for different profiles. The worker splits the queue by profile
id and runs one synthesis call per group. The model copy is shared.

Limits:
- One synthesis call uses one profile id. A live HTTP batch can mix ids; the
  worker splits it into one call per profile.
- True mixed-profile GPU batches are not supported now. They need a per-row
  stacked voice state and a full audio test. Treat that as a future option.
- Texts in one profile group must have equal first-chunk token lengths.
- A profile request with mixed first-chunk token lengths returns 422.
- The server groups by first-chunk token length automatically. You do not sort.

## Why first-chunk token lengths must match

The conditioned KV state has one fixed prefix length. Each row then adds text
tokens. If two rows have different text token counts, their KV positions no
longer align. The batch can then emit silence or too much audio.

Example:
- `"Hi."` gives 2 tokens.
- `"Please read this sentence."` gives 5 tokens.

If these two texts share one conditioned batch, the rows differ. Bad audio can
result. Put each text in its own group, or make the counts equal.

Ways good engineers handle it:
1. Group rows by token count. This is safe and keeps batching. The server does
   this now.
2. Pad each row to one length and use a correct attention mask and per-row
   positions. This can allow mixed lengths in one call, but it needs model
   changes and full audio tests. It is not done here.
3. Run one text per call. Simple but slower.

## Image and Modal wiring

At image build time:
1. Run `Code/batch/build_voice_cache.py`. Set `ARSENAL_VOICE_CACHE` to its output.
2. Run `Code/batch/build_voice_profiles.py`. Set `ARSENAL_VOICE_PROFILES`.

Keep both outputs in the image or on a Modal Volume:
- Image layer: reproducible. A new container has the files. A warm container
  also keeps them.
- Modal Volume: persists across sleep, wake, and new containers. Use it for many
  voices that change often.
- Do not put 50 profile files in git. Use a Volume, or bake a small set.

Sleep and wake:
- A warm container keeps its filesystem.
- A new container gets the image layers or mounts the Volume.
- The cache must not be rebuilt on every wake. Build it once, then reuse it.

## Checklist

- [ ] Profile files built.
- [ ] `ARSENAL_VOICE_PROFILES` set for every id.
- [ ] Voice cache built and `ARSENAL_VOICE_CACHE` set.
- [ ] Default request uses the reference clip.
- [ ] Profile request returns 200.
- [ ] Unknown id returns 400.
- [ ] Mixed profile batch returns 422.
