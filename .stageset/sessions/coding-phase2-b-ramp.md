---
type: CODING
time: 2026-11-22T15:25:30+05:30
summary: Run Phase 2 B-ramp for sentence and utterance; max stable B224.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; LivingDocs/SSLD-024-phase2-b-ramp.md; Code/probes/probe_phase2_bramp.py; Code/probes/out/phase2_bramp/ramp.json; .stageset/runs/20261122-152530-RUN.md
related: IDEA-0008; SSLD-024; 20261122-152530-RUN; FACT-0151
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Test both modes, first_only=1, short text, 3 reps.

## Outcomes

- B<=224 stable 350ms for both modes, 0 errors.
- B>=320 splits/tails; max stable 350ms B=224.
- 200ms gate B<=64; 100ms not met.

## Follow-up

- Investigate B320/448 formation/admission split.
- Run mixed short+long and Poisson ramp.
