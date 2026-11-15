---
type: MAINTENANCE
time: "2026-11-15T12:47:13+05:30"
summary: Integrate batch 1 plans and fix skeleton metadata for the Phase 0 setup and probe.
paths: .gitignore; Ideas/pocket-tts-multilingual-optimization.md; LivingDocs/SSLD-001-setup-env.md; LivingDocs/SSLD-002-probe-model.md; LivingDocs/SSLD-003-benchmark-harness.md; Skeletons/requirements.txt.skeleton.md; Skeletons/Probes/probe_model.md; .stageset/report.json
related: IDEA-0001; SSLD-001; SSLD-002; SSLD-003
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Adopt the batch 1 layout: the model goes to `Code/model`, and the probe goes to `Code/probes/`.
- Split Phase 0 into three focused ss-living-docs. Each doc has a clear next step.
- Keep one idea file: `Ideas/pocket-tts-multilingual-optimization.md`. Drop the duplicate idea draft.
- The probe is a `PROBE` skeleton. It is not an `IMPLEMENTATION` skeleton.

## Outcomes

- Added `Skeletons/requirements.txt.skeleton.md` with correct version 2 metadata.
- Added `Skeletons/Probes/probe_model.md` with 7 sections and assumptions A-01 to A-05.
- Added `SSLD-001-setup-env.md` and `SSLD-002-probe-model.md`.
- Moved the old Phase 0 plan to `SSLD-003-benchmark-harness.md` and removed the duplicate setup tasks.
- Added `.gitignore` for `Code/model/` and `Code/probes/out/`.
- Added the probe map to the idea file.

## Follow-up

- Run `python scripts/ss-living-doc.py LivingDocs/SSLD-001-setup-env.md --next` to start.
- Put a real reference voice at `Code/probes/ref/voice.wav` before SSLD-002 T002.
- Run the probe. Use the JSON output to fill `.stageset/facts.md` with a `PROBE` run report.
