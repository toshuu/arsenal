---
type: CODING
time: "2026-11-15T13:02:25+05:30"
summary: Complete SSLD-001 setup, install pocket-tts, and download the model.
paths: Code/requirements.txt; Code/model/; Skeletons/requirements.txt.skeleton.md; LivingDocs/SSLD-001-setup-env.md; .stageset/runs/20261115-130213-RUN.md; .stageset/runs/20261115-130213-RUN-02.md
related: IDEA-0001; SSLD-001; 20261115-130213-RUN; 20261115-130213-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Install the PyPI package `pocket-tts` version 4.0.1.
- Download the full model repo into `Code/model`, not only three files.

## Outcomes

- `Code/requirements.txt` has the 3 packages.
- `pocket_tts` imports and exposes the public API.
- `Code/model` holds 419 MB. The config has 6 layers, 24 kHz, and 12.5 Hz frames.
- All 4 tasks of SSLD-001 are DONE.
- `Skeletons/requirements.txt.skeleton.md` is DONE at revision 1.

## Follow-up

- Run SSLD-002 to create and run the probe.
- Put a real reference voice at `Code/probes/ref/voice.wav` before the probe.
