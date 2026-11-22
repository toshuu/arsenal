---
type: MAINTENANCE
time: 2026-11-22T23:24:57+05:30
summary: Document B thresholds, first-chunk cause, mode check, and the owner choice of sentence mode for WS.
paths: .stageset/runs/20261122-232457-RUN.md; .stageset/facts.md; Ideas/IDEA-0008-natural-live-call-streaming.md
related: IDEA-0008; FACT-0139; FACT-0158; FACT-0159; FACT-0160; 20261122-232457-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Work

- Swept B on the current app with default voice and with conditioned voice `v1`.
- Recorded first-sound B thresholds at 100, 200, 300, and 350 ms.
- Checked the WS path clock. The first binary audio frame is the endpoint.
- Checked the server code. Three modes exist: `sentence`, `utterance`, `latency`.
- Traced the 2026-11-21 B=320 result to an older 8-frame first chunk.

## Result

The owner chose `sentence` mode with the about-40-frame first chunk for WS.
All three modes stay selectable from the API payload. No app code change.

Raw data is in `Code/probes/out/ws_burst_gate/sweep_20261122-232457.json`.
