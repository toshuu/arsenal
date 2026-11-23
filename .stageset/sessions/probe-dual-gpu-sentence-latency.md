---
type: PROBE
time: 2026-11-23T15:31:27+05:30
summary: Re-measure sentence mode and the 24-frame latency tier on two GPUs with both voices.
paths: Code/probes/out/ws_burst_gate/sweep_20261123_dual_gpu; .stageset/facts.md
related: IDEA-0008; FACT-0164; FACT-0165; 20261123-153127-RUN; 20261123-153127-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Work

- Ran two servers in parallel. Sentence mode on GPU 0, cores 0-1. Latency tier
  on GPU 1, cores 2-3.
- Tested the default voice and conditioned voice `v1` in each mode.
- Used pre-connected WS clients. Clocked only the first audio byte.
- Used 2 warmups and 4 measured reps at 14 B values per voice.

## Result

- Conditioned voice still gives lower first-sound time from B=48 upward in
  sentence mode and from B=96 upward in the 24-frame latency tier.
- Conditioned voice is slower at B=8 by about 19 to 25 ms p50.
- Sentence mode gates today: default 32/64/128/160 ms B for 100/200/300/350;
  conditioned 32/128/192/256.
- Latency tier gates today: default 8/48/64/96; conditioned none/48/64/128.

## Follow-up

- Confirm the gates with one server at a time if the owner needs a clean gate.
- Investigate the fixed conditioned cost at low B.
