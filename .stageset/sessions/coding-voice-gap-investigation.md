---
type: CODING
time: 2026-11-15T18:49:10+05:30
summary: Explain the voice length TTFA gap as a cross-process measurement bias.
paths: Code/probes/debug/check_voice_ttfa.py; Code/probes/debug/check_voice_cut.py; Code/probes/debug/check_voice_onset.py; .stageset/runs/20261115-184910-RUN.md; .stageset/facts.md
related: IDEA-0003; SSLD-008; 20261115-184344-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Treat FACT-0019 as measured values with a biased ranking.
- Do not compare lever configs across separate subprocess runs.
- Keep the defaults unchanged until the harness runs all configs in one process.

## Outcomes

- In-process test: shorter voice is faster. 4.0 s 163.8 ms, 3.0 s 145.2 ms, 2.0 s 130.0 ms at B=96.
- Prefix width follows the voice length: 51, 39, 26 frames.
- The 4.0 s advantage in FACT-0019 is a subprocess bias, not a model property.
- Truncation order was checked. It does not change the frame count much.

## Follow-up

- Change the probe to run all configs in one process.
- Set the operating point after that clean run. Candidate: voice 3.0 s.
- Then Phase D RTF work.
