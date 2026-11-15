---
type: IDEATION
time: "2026-11-15T13:11:27+05:30"
summary: Plan the T4 GPU single-stream baseline probe and the results panel.
paths: Skeletons/Probes/bench_gpu.md; LivingDocs/SSLD-004-gpu-baseline.md; scripts/stageset-report.py; viewer/index.html; .stageset/results.json; .stageset/report-format.md
related: IDEA-0001; SSLD-004
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Measure one T4 GPU stream. Use 3 warmup runs and 20 measured runs.
- Measure first chunk, first non-silent chunk, RTF, peak VRAM, and leading silence.
- Add a `results` array to `report.json`. Read it from `.stageset/results.json`.
- Show the results in the viewer as cards with large metric values.

## Outcomes

- The report schema now has a `results` field.
- The viewer now has a Results panel.
- The plan has a GPU probe skeleton and a step list.

## Follow-up

- Run SSLD-004 on the T4.
- Add the GPU numbers to `.stageset/results.json`.
