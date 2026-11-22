---
type: MAINTENANCE
time: 2026-11-22T16:49:18+00:00
summary: Spec 4 for the WS gate. Add quiet formation and sentence/utterance comparison.
paths: Skeletons/Probes/probe_ws_burst_gate.md; LivingDocs/SSLD-033-formation-modes.md
related: IDEA-0008; SSLD-032; 20261122-230000-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Result to explain

SSLD-032 is valid. The gate failed.

- B=224 `sentence`: p50 414.74 ms, p95 469.51 ms, 0 errors.
- B=320 `sentence`: p50 523.11 ms, p95 587.03 ms, 0 errors.

The probe used cap 448 and the default formation. The 224 calls never reach
the target of 448 rows. So the collector waits the full 150 ms window before
it closes the batch.

## Phase gap

- The WS `sentence` first chunk is the whole short sentence, about 40 frames.
  The Phase 4 315 ms result truncated the first chunk to 8 frames in the debug
  path. The two clocks are not comparable.
- All raw modes stream frames as they come. `utterance` is one chunk with a
  512-frame cap. It was slower than `sentence` in Phase 0 at B=64.
- The server has a call-first quiet path. It closes the batch when all active
  calls are present, or after a quiet gap. The gate did not enable it.

## Spec 4 change

- Enable `ARSENAL_CALL_FIRST_QUIET_MS=5` and `MIN_EARLY=32`. Keep the window
  at 150 ms as a bound.
- Set cap 640. This matches Phase 4.
- Compare `sentence` and `utterance` over the real WS path at B=224 and B=320.
- Pick `utterance` if it passes and is within 10 ms of `sentence`. Else pick
  the passing mode with the lower p95.
- Record `call_first_wait_ms` and `batch_wait_ms` to show the formation wait.

## Non-goals

- No app code change.
- No first-chunk resize.
- No commit.
