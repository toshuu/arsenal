---
type: CODING
time: 2026-11-21 12:39 +0530
summary: Pause B-ceiling; fix call chunking naturalness (sentence-level), cap-hit/integrity logging, listening pack, start burst/Poisson re-measure.
paths: Code/batch/call_chunker.py; Code/batch/server.py; Code/batch/audio_join.py; Code/probes/out/quality/call_live_1.wav; Code/probes/out/quality/call_live_2.wav; Code/probes/out/quality/call_live_3.wav; Code/probes/out/quality/call_live_4.wav; Code/probes/out/quality/call_live_5.wav; Code/probes/out/quality/ref_1.wav; Code/probes/out/quality/ref_2.wav; Code/probes/out/quality/ref_3.wav; Code/probes/out/quality/ref_4.wav; Code/probes/out/quality/ref_5.wav; Code/probes/out/quality/manifest_live.json; .stageset/runs/20261121-123900-RUN.md
related: IDEA-0007; 20261121-123900-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions
- Naturalness first; B-ceiling paused until owner listening passes.
- Sentence-level call chunking only: first chunk first complete sentence (cap ~25 words, long sentence split at strongest clause boundary), later chunks following sentences; no intra-sentence splits otherwise.
- Frame cap per chunk = `tokens*3+16`, clamp 24-192; assert no cap-hit.
- Length-bucketed call_first batching enabled (`ARSENAL_CALL_FIRST_BUCKETS=1`, <=24/48/96/192).
- Model-internal pauses accepted (option 3); no special case for short single-sentence utterances.

## Outcomes
- Fixed missing-word risk: generous frame cap, cap_hit/eos/audio_sec logged per WS chunk, text integrity assert.
- Listening pack regenerated: `call_live_1..5.wav` with 2 sentence-boundary chunks each, 0 cap-hit, integrity true, ratios 0.923-1.094.
- Owner ear: old mid-phrase/greeting splits gone; remaining pauses are model-internal inside chunks.
- WS raw PCM path still not smoothed; HTTP call paths smoothed.
- Burst/Poisson measurement script launched (`/tmp/run_quality_measure.py`), results may be incomplete.

## Follow-up
- Wire join smoothing/gap targets into WS `/ws/tts`.
- Complete burst B=64/128/192/256 and Poisson 64/128/192 pre-connected 30s; record results.
- Owner listening gate before Modal/mixed/overhead.
