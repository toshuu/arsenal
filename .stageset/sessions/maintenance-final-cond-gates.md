---
type: MAINTENANCE
time: 2026-11-23T16:21:17+05:30
summary: Record the final conditioned-voice gate table for both tiers on one B grid.
paths: Code/probes/out/ws_burst_gate/final_cond_gates_20261123; .stageset/facts.md
related: IDEA-0008; FACT-0168; FACT-0169; FACT-0170; 20261123-162117-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Work

- Measured the conditioned voice on the same B grid in both tiers.
- Ran one server at a time. Used 2 warmups and 4 measured reps.
- Used median per-rep p95 so one bad rep does not set a gate.

## Result

- Final gates, latency / sentence: 100 ms 48/48, 120 ms 64/64, 150 ms 96/80,
  200 ms 128/128, 250 ms 160/160, 300 ms 224/192, 350 ms 256/224.
- All 26 rows had 0 errors.

## Follow-up

- Use the latency tier when the 300 or 350 ms gate matters.
- Use either tier at 100, 120, 200, or 250 ms.
