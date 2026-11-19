---
type: CODING
time: 2026-11-19T19:55:00+05:30
summary: Fix mixed-length voice profile calls. Use the normal voice path for that call. No 422.
paths: Code/batch/server.py; Code/probes/check_server.py; docs/voice-profiles.md; Code/batch/VOICE_PROFILES.md; Skeletons/Code/batch/server.py; .stageset/facts.md
related: IDEA-0005; FACT-0093; FACT-0094; FACT-0095
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- A conditioned call needs equal first-chunk token lengths.
- If one profile call has mixed lengths, use the normal voice path for that call.
- The voice still comes from the same profile.
- Do not reject the request. No 422.
- Group jobs by profile id only. Let the engine pick the path.

## Outcomes

- Mixed-length profile batch returns 200 with correct sample counts.
- No 5 s overrun.
- Uniform profile batch still uses the conditioned path.
- The fake-engine probe passes 12 checks.
- Validate passes.

## Open items

- A true mixed-length conditioned call needs model-level mask and position changes. Not done.
