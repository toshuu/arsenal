---
type: CODING
time: "2026-11-15T13:13:02+05:30"
summary: Complete SSLD-004 T4 GPU baseline and publish the results.
paths: Code/probes/bench_gpu.py; Code/probes/out/; Skeletons/Probes/bench_gpu.md; LivingDocs/SSLD-004-gpu-baseline.md; .stageset/runs/20261115-131244-RUN.md; .stageset/runs/20261115-131244-RUN-02.md; .stageset/results.json; .stageset/facts.md; scripts/stageset-report.py; viewer/index.html; .stageset/report-format.md
related: IDEA-0001; SSLD-004; 20261115-131244-RUN; 20261115-131244-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Measure one T4 stream with 3 warmup runs and 20 measured runs.
- Add a `results` field to the report and a Results panel to the viewer.
- Keep the full result list in `.stageset/results.json`.

## Outcomes

- T4 p50 first chunk is 47.942 ms. p95 is 56.273 ms.
- T4 p50 RTF is 0.234. p95 is 0.258.
- Peak allocated VRAM is 496.0 MB.
- Load is 0.991 s. Voice prefix is 0.485 s.
- All 4 tasks of SSLD-004 are DONE.
- The report and viewer now show big results as metric cards.

## Follow-up

- Run a fixed-seed test for the leading-silence difference.
- Plan a burst and sustained concurrency test.
