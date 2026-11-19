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
- One conditioned call uses one profile id. A live HTTP batch can mix ids; the
  server uses the normal path with per-row voices for that call.
- Mixed profiles in one GPU call now use the normal path with per-row voice
  tensors. The conditioned fast path still needs one profile id and equal
  first-chunk token lengths.
- A conditioned call needs equal first-chunk token lengths.
- If one profile call has mixed lengths, the server uses the normal voice path
  for that call. The voice still comes from the same profile. No 422. No bad
  audio. The server chooses this automatically.
- The server groups by profile id. You do not sort texts.

## Why first-chunk token lengths must match

The conditioned KV state has one fixed prefix length. Each row then adds text
tokens. If two rows have different text token counts, their KV positions no
longer align. The batch can then emit silence or too much audio.

Example:
- `"Hi."` gives 2 tokens.
- `"Please read this sentence."` gives 5 tokens.

If these two texts share one conditioned batch, the rows differ. Bad audio can
result. The server detects this and uses the normal path for the call. It does
not reject the request.

Ways good engineers handle it:
1. Use the normal path when lengths differ. This is safe and keeps one call. The
   server does this now.
2. Group rows by token count. This keeps the conditioned fast path per group. It
   can need several calls.
3. Pad each row to one length and use a correct attention mask and per-row
   positions inside the conditioned state. This can allow mixed lengths in one
   conditioned call, but it needs model changes and full audio tests. It is not
   done here.

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
- [ ] Mixed profile batch returns 200.
