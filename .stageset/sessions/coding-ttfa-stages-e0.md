---
type: CODING
time: 2026-11-16T13:00:00+05:30
summary: Run E0 stage probe; the 50 to 180 ms gap is not present with a separate-process client.
paths: Code/batch/batched_stream.py; Code/probes/probe_ttfa_stages.py; Code/probes/out/probe_ttfa_stages.json; .stageset/facts.md; Skeletons/Code/batch/batched_stream.py; Skeletons/Probes/probe_ttfa_stages.md
related: IDEA-0004; FACT-0041; FACT-0043; FACT-0044; FACT-0045; 20261116-125702-RUN; 20261116-125702-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Add only a cheap `on_stage` callback to `BatchedStream.stream()`. Do not
  change the hot path.
- Measure from a separate load-generator process. Do not synchronize the GPU
  inside the stream callback.

## Outcomes

- B=128 p95 TTFA is 186.13 ms (640/640 <350).
- B=160 p95 TTFA is 216.06 ms (800/800 <350).
- The stage sum matches TTFA p95 within 0.001 ms. The queue cost is under 0.72 ms.
- Text prep is the largest stage: 65.4 ms at B=128 and 84.7 ms at B=160.
- First-emit row iteration is 25.9 ms at B=128 and 34.0 ms at B=160.
- GPU util is 71.25% mean. The GPU is not saturated.

## Follow-up

- E1: move text prep off the critical path. Largest measured gain.
- E2: check the Mimi decoder dtype. `enable_fp16_backbone` still decodes in FP32.
- Run a paired probe with the old in-process client to prove the earlier tail
  was a measurement artifact.
- Do not start E3, E4, E7, M1 or M2 before E1 and E2 are measured.
