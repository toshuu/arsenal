---
type: CODING
time: 2026-11-21 12:15 +0530
summary: Finalize call quality (pause compression, single-chunk), diagnose A-vs-B pause, attempt B re-measure, stop Modal GPU.
paths: Code/batch/pause_compress.py; Code/batch/server.py; Code/batch/call_chunker.py; Code/deploy/modal_app.py; Code/probes/pc_poisson.py; Code/probes/out/quality/call_live_1.wav; Code/probes/out/quality/call_live_2.wav; Code/probes/out/quality/call_live_3.wav; Code/probes/out/quality/call_live_4.wav; Code/probes/out/quality/call_live_5.wav; Code/probes/out/quality/manifest_live.json; .stageset/runs/20261121-121500-RUN.md; .stageset/facts.md; .stageset/reports/20261121-call-mode-local-maxb/results.json
related: IDEA-0007; 20261121-121500-RUN; FACT-0146
commit: 94a2e57 f0e35ef 20372b1 800313b 6ce4aa7 a29b457
remote: origin/main
branch: main
---

# Session notes

## Decisions
- Naturalness first; B/Mixed/Modal workload parked until owner listen gate.
- Pause compression accepted; keep `ARSENAL_CALL_PAUSE_MAX_MS=250` on WS path.
- HTTP single-chunk responses skip join smoothing/compression.
- No fix for A-vs-B pause (would change chunking/TTFT); needs owner approval.
- Modal GPU stopped immediately on probe stall; 0 containers active.

## Outcomes
- Listening pack regenerated (single-chunk, compressed pauses ~250ms), integrity/cap checks pass.
- Pause diagnosis: A vs B differs (304 vs 359ms p50) with identical text/token ids -> call path cause. Cap 192 best; smaller caps worse.
- Compression CPU ~8.5-9.7ms per 1.5s audio.
- B/Poisson numbers NOT captured: probe client hangs local + Modal; all apps stopped.

## Follow-up
1. Fix `call_load_client` / Poisson prober hang before any B work.
2. Owner listens `call_live_1..5.wav`; decide A-vs-B pause fix.
3. Then burst 64/128/192/256 + Poisson 64/128/192 (one server, /debug/drain between cases); stop GPU after.
