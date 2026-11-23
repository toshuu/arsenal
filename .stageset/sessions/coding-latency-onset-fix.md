---
type: CODING
time: 2026-11-23T16:09:27+05:30
summary: Send the first latency PCM frame raw; leave sentence and utterance paths unchanged.
paths: Code/batch/server.py; Skeletons/Code/batch/server.py; Code/probes/out/ws_burst_gate/onset_fix_20261123
related: IDEA-0008; FACT-0167; FACT-0168; FACT-0169; 20261123-160927-RUN; 20261123-160927-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Decision

The owner approved a fix for the latency tier only. Sentence mode stays as it
is. No change to the pause compressor file.

## Work

- In the WS sender, send the first frame of a latency chunk as raw PCM. Start
  the pause compressor with the second frame.
- Sentence and utterance have no compressor. Their path is unchanged.
- Updated the server skeleton to revision 12 and added CHECK-SERVER-13.
- Ran compile check, mode check, stage A/B, and one-server B sweeps.

## Result

- Latency first-emit-to-byte max falls from 204.07 ms to 14.64 ms.
- Latency client p95 falls from 176.73 ms to 108.98 ms at B=48.
- Latency gates: default 200 ms B=96, conditioned 200 ms B=128 and 350 ms B=256.
- Sentence conditioned gates stay at 48 / 128 / 192 / 256.

## Follow-up

- The 100 ms gate is still not met at B=48 in the latency tier.
- Consider the holdback knob if the owner wants the last 10 ms. It is not changed here.
