---
type: CODING
time: 2026-11-15T18:43:44+05:30
summary: Run the randomized lever probe and pick voice 4.0 s with a 16-token cap.
paths: Code/probes/probe_prefill_random.py; Code/probes/pick_lever.py; Skeletons/Probes/probe_prefill_random.md; .stageset/runs/20261115-184344-RUN.md; .stageset/facts.md
related: IDEA-0003; SSLD-008; 20261115-182905-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Repeat the lever probe with random order, seed 7, and 3 bursts.
- Pick a pair that meets 350 ms at both B=96 and B=128.

## Outcomes

- Best pair: voice 4.0 s, first-token cap 16.
- p95 TTFA: 233.4 ms at B=96 and 247.3 ms at B=128 on T4 with FP16.
- B=128 meets the target with the levers. The Phase C stretch target is reached.
- Shorter voices (3.0 and 2.0 s) are slower than 4.0 s. Cause unknown.
- FACT-0019 records the result.

## Follow-up

- Explain the 4.0 s versus 3.0 s gap before a default is set.
- Then run Phase D RTF work at B=128 to 160.
