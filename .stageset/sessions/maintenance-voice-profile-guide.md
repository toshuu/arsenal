---
type: MAINTENANCE
time: 2026-11-19T19:35:00+05:30
summary: Add a long-term voice profile guide. Document Modal cache/profile persistence and mixed-profile batching.
paths: docs/voice-profiles.md; Code/batch/VOICE_PROFILES.md; Code/batch/build_voice_cache.py; LivingDocs/SSLD-017-modal-deployment-plan.md; README.md; .stageset/facts.md
related: IDEA-0005; FACT-0066; FACT-0093; FACT-0094
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- `docs/voice-profiles.md` is the long-term guide. README points to it.
- The Modal image must build the voice cache and the profiles once.
- Keep the cache and profiles in the image or on a Volume. Do not rebuild on wake.
- One GPU call uses one profile id. A mixed HTTP batch is split per profile.
- True mixed-profile GPU batching is a future option, not current.

## Outcomes

- Build and use steps are in one file.
- The first-chunk token length limit has an example.
- Modal sleep/wake behavior is documented.
- StageSet validate passes.
