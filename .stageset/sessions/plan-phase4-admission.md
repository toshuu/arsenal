---
type: IDEATION
time: 2026-11-22T19:21:50+05:30
summary: Plan Phase 4 admission. Test the cap before a BatchedStream change.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; Skeletons/Probes/probe_phase4_admission.md; LivingDocs/SSLD-025-phase4-admission.md
related: IDEA-0008; FACT-0151
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Phase 2 split B=320 and B=448 into two batches.
- The default cap is 224 rows. The older in-process sweep shows B=384 in one batch at a cap of 640.
- Test the cap on the current code before any `BatchedStream` API change.
- Use the `sentence` and `utterance` modes. Use B=224, 320, 448. Use `first_max_frames=8`.
- If B=320 is one batch and p95 <= 350 ms, Phase 4 is a cap and formation change.
- If B=320 splits or p95 > 350 ms, Phase 4 needs a code change.

## Outcomes

- Added `Skeletons/Probes/probe_phase4_admission.md`.
- Added `LivingDocs/SSLD-025-phase4-admission.md`.

## Follow-up

- The coder runs SSLD-025. The planner reads the run report and updates the facts.
