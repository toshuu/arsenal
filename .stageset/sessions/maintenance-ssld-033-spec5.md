---
type: MAINTENANCE
time: 2026-11-22T17:10:00+00:00
summary: Spec 5 for the WS gate. Restore the confirmed formation settings and drop utterance.
paths: Skeletons/Probes/probe_ws_burst_gate.md; LivingDocs/SSLD-033-formation-modes.md
related: IDEA-0008; SSLD-033; 20261122-235500-RUN; FACT-0139
commit: -
remote: -
branch: -
---

# Session notes

## Block

SSLD-033 T003 was BLOCKED.

- `utterance` forces 512 frames per row. At B=224 this OOMs on T4.
- `quiet=5` with `MIN_EARLY=32` closed the batch after about 32 arrivals.
  The 224-call burst split into about 7 serial batches. Sentence p95 became
  1878 ms.

## Fix

Use the settings that passed in FACT-0139:

- cap 640, BATCH_TARGET 640, MAX_FRAMES 192
- CALL_FIRST_MAX_FRAMES 8
- quiet 50, hard cap 300, grace 20
- no MIN_EARLY override
- prewarm on

Test `sentence` only, at B=224, 320, 384. Add `--max-frames 8` to the client.

## Decision

Keep both modes in the app. The low-latency config is the default for voice
calls. Mode is selectable per request from the WS `start` payload and the text
payload. No app code change in this spec.

## Non-goals

- No utterance comparison.
- No app code change.
- No commit.
