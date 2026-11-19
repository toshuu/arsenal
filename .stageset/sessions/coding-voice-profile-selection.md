---
type: CODING
time: 2026-11-19T19:31:00+05:30
summary: Add per-request voice profile selection. Default is the reference clip. Add profile build script.
paths: Code/batch/server.py; Code/batch/build_voice_profiles.py; Code/probes/check_server.py; Code/batch/VOICE_PROFILES.md; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0066; FACT-0093; FACT-0091
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- A request without `voice_profile` uses the reference voice clip (normal path).
- A request with `voice_profile` uses the conditioned profile with that id.
- The server reads ids from `ARSENAL_VOICE_PROFILES`.
- An unknown id returns 400.
- A profile batch must have equal first-chunk token lengths, else 422.
- The worker groups jobs by profile id and first-chunk token length.

## Outcomes

- `build_voice_profiles.py` writes conditioned profiles at image time.
- The fake-engine probe passes 12 checks.
- The real engine serves default and profile requests with 200.
- Unknown profile returns 400.
- `--validate` passes.

## Open items

- Modal image must run `build_voice_profiles.py` and set `ARSENAL_VOICE_PROFILES`. That is Modal scope.
