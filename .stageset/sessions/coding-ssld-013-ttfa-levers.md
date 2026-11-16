---
type: CODING
time: 2026-11-16T13:20:00+05:30
summary: E1/E4/E2/E3 and max-B. Prep 65->2.2 ms, emit 26->0.28 ms, B=160 soak 100% under 350.
paths: Code/batch/batched_stream.py; Code/batch/fp16.py; Code/probes/probe_ttfa_stages.py; Code/probes/check_mimi_fp16.py; Code/probes/out/probe_ttfa_maxb.json; Code/probes/out/probe_ttfa_mimi_autocast.json; Code/probes/out/probe_ttfa_soak_144_160.json; Code/probes/out/soak_b144_summary.json; .stageset/facts.md; Ideas/optimization-strategy.md; Skeletons/Code/batch/batched_stream.py; Skeletons/Code/batch/fp16.py; LivingDocs/SSLD-010-gpu-agnostic-optim.md; LivingDocs/SSLD-013-ttfa-levers.md
related: IDEA-0004; SSLD-013; SSLD-010; FACT-0046; FACT-0047; FACT-0048; FACT-0049; FACT-0050; FACT-0051
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use the clean separate-process client for every number.
- E1: one worker pool and one batched embedding call. Keep an id cache.
- E4: append frame views and keep a `row_ids` map. No per-row clone.
- E2: run Mimi decode under FP16 autocast. Keep the parameters in FP32.
  `.half()` breaks the conv dtype.
- E3: drop decode_group 2 and 4. Both are slower.

## Outcomes

- Prep p50 65.4 -> 2.22 ms at B=128. Emit p50 25.9 -> 0.277 ms.
- Warm p50 TTFA at B=128/160/192/224: 67.6/78.8/91.6/107.1 ms.
- Autocast Mimi steady at B=160: 79.1 -> 65.4 ms.
- Clean soak: B=144 p95 84.1 ms; B=160 p95 95.0 ms. Both 100% under 350.
- B=256 is OOM on one T4.

## Follow-up

- SSLD-014: M2 (Mimi on a second stream), then M1 (workers per GPU).
- Add a cold-start prewarm for autocast kernels before production.
- Owner listening gate for the autocast Mimi WAVs is still open.
