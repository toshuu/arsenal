---
id: IDEA-0008
title: Natural live-call streaming engine - quality, high B, and no tail wait
status: SKELETONIZED
priority: P0
created_at: 2026-11-22T14:10:20+05:30
created_in: .stageset/sessions/plan-natural-streaming.md
updated_in: .stageset/sessions/maintenance-phase4-quiet-fix-review.md
updated_at: 2026-11-22T20:20:00+05:30
related_ideas: [IDEA-0007, IDEA-0005]
related_skeletons:
  - Skeletons/Probes/probe_natural_stream.md
  - Skeletons/Code/batch/server.py
related_reports: [.stageset/runs/20261122-142726-RUN.md, .stageset/runs/20261122-144709-RUN.md, .stageset/runs/20261122-144710-RUN.md, .stageset/runs/20261122-150820-RUN.md, .stageset/runs/20261122-151455-RUN.md, .stageset/runs/20261122-152530-RUN.md]
---

# Natural live-call streaming engine

## Goal

Build one WebSocket call engine that gives all four results together:

1. Natural speech. No mid-clause cut. No fixed join pause. No pause clipping.
2. High B under burst. Target 350 ms first-sound p95.
3. Low first-sound latency. Target 200 ms at medium B and 100 ms at low B.
4. Raw PCM frames sent as the model generates them.

The connection is already open. The clock starts when the server receives the
text message. The clock stops at the first audio byte on the WebSocket.

## What is already built

These parts exist and work. Do not rebuild them.

- Frame streaming: `BatchedStream._stream_single` calls `on_chunk` for each
  decoded frame. `Code/batch/batched_stream.py:445`.
- Per-row EOS: each row stops at its own EOS. The batch stops when all rows stop
  or reach `max_frames`.
- Row compaction: finished rows leave the GPU batch every `B/8` rows.
  `compact=True`. `Code/batch/batched_stream.py:665`.
- Low-latency decode: `decode_group=1` emits each frame with no extra wait.
- Overlap decode: `Code/batch/overlap.py` can hide Mimi decode behind the next
  flow step.
- Voice KV reuse: conditioned profiles cut first-frame work. `build_voice_profiles.py`.
- Job classes and priority: `call_first > call_cont > normal`.
  `Code/batch/job_classes.py`.
- WS frame send: the call WS sends PCM as frames arrive.
  `Code/batch/server.py:1634`.
- Sentence chunker: `Code/batch/call_chunker.py`. It already keeps 35 words or
  fewer as one chunk.

## What is wrong now

1. `max_first_tokens=16` cuts the first chunk at 16 tokens. This can cut inside
   a clause. Example: after "we" in "Life ... the way we | plan, but ...".
   `Code/batch/batched_stream.py:284`.
2. `BatchedStream` re-chunks a text after `call_chunker` returns it. A "single
   chunk" from call mode can still split inside the model path.
3. `pause_compress.py` caps any silence over 250 ms to 250 ms. This clips
   natural pauses.
4. `join_chunks()` adds a fixed 100 ms pause between chunks.
5. The WS call path submits one chunk at a time and waits for that job.
6. A batch accepts no new rows while it runs. New calls wait for the longest
   row in the current batch. Compaction shrinks compute, but it does not admit
   new calls.

## Strategy

Use three layers. Each layer has one job.

### Layer 1: Raw frame streaming

- Always send model frames as they arrive.
- Do not transform audio in the natural path.
- No pause compression. No fixed join pause. No RMS change.
- Keep `decode_group=1`. Keep `compact=True`.
- Use `overlap_decode` when the probe shows a gain.

### Layer 2: Text policy

Use one of three modes. Select by load and text size.

| Mode | Chunk rule | Use |
| --- | --- | --- |
| `utterance` | One job for the whole text. No first-token cut. | Low load. Fallback for one short utterance. |
| `sentence` | Split only at sentence ends. No first-token cut. Cap 24 to 32 words. | Default. Best balance of quality, B, and first-frame time. |
| `latency` | Split at the first strong clause. First cap 24 to 32 tokens. | Extreme load only. |

Rules:

- Never split inside a clause for quality.
- Never apply `max_first_tokens=16`.
- If a sentence must split, split at `, ; :` and keep the punctuation.
- Keep the text short enough to avoid `max_frames` truncation.

### Layer 3: Late join

Goal: a new call does not wait for the longest row.

Two steps:

1. Short term: bound job length with `sentence` mode. This makes the tail
   small. A new call waits for one sentence, not one full utterance.
2. Long term: add continuous admission. At each model step, remove finished
   rows (already done) and add waiting rows to free slots. This needs a
   `BatchedStream` API change: resize state and prefix, and set pad for new
   rows. Do this only after Phase 0 proves the need.

## Target gates

These are goals, not facts. Phase 0 measures the real floor.

| Gate | Goal B | Notes |
| --- | ---: | --- |
| 350 ms | 224 to 448 | Must pass. Main gate. |
| 200 ms | 96 to 224 | Likely on T4 with short first chunk. |
| 100 ms | 32 to 96 | Low B. Do not promise at B=224. |

T4 facts: direct first emit at B=224 was 97.7 ms. Conditioned p95 was 112.2 ms.
So 100 ms p95 at B=224 is not possible with the current model. Report the floor.

## Phase 0 result

SSLD-022 ran on a local T4 at B=64. The first repetition is cold. The values
below use only warm repetitions.

| Mode | Mix | First-frame p95 | Batch wall p50 | Tail |
| --- | --- | ---: | ---: | --- |
| `legacy` | same | 97.26 ms | 6661.56 ms | 6.14 to 6.62 s |
| `sentence` | same | 122.10 ms | 6314.41 ms | 5.95 to 6.29 s |
| `utterance` | same | 181.31 ms | 6201.34 ms | 5.20 to 6.05 s |
| `sentence` | mixed | 284.62 ms | 7973.10 ms | 0.88 to 7.95 s |
| `utterance` | mixed | 337.57 ms | 7577.40 ms | 0.92 to 7.54 s |

Readings:

- `utterance` passes the 200 ms gate at B=64 with one long text. It does not
  pass 100 ms. Only the 16-token `legacy` cut passes 100 ms.
- `sentence` passes 200 ms for one long text. It costs about 60 ms over
  `legacy` at B=64.
- Mixed text raises first-frame time. Short rows wait for the long row prefill
  in the same batch. `utterance` mixed is 337.57 ms, still under 350 ms.
- Compaction works. Short rows finish below 1 s while long rows run for about
  7.5 s. New calls still cannot join. Tail wait is real.
- The `utterance` WAV has pauses of 231 to 519 ms at commas and sentence ends.
  The `legacy` WAV has a 620 ms gap at 13.93 s. Owner listening is still open.
- Phase 0 used B=64 only. It does not prove B=224 to 448. It does not prove a
  server path. It does not prove naturalness by ear.

Implications:

- Use `utterance` for low load and best quality. Use `sentence` for high load.
  Keep `latency` for extreme load only.
- Add first-chunk size buckets for mixed text. Do not put a 2 s row and an 18 s
  row in the same first batch if a 200 ms gate is needed.
- Run Phase 2 on the server at B=224 and B=448. Use short first chunks for the
  350 ms gate. Do not use the whole 18 s utterance as the high-B first chunk.
- The probe now resolves a relative `--out` path before `chdir`, writes WAVs
  next to the JSON, and reports cold and warm values separately.

## Phase 2 B-ramp

Local T4, `/debug/callramp`, `first_only=1`, short text, 3 reps, warm reps 1-2:

| Mode | B32 | B64 | B96 | B128 | B224 | B320 | B448 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sentence | 193 | 209 | 236 | 261 | 210 | split 361-1373 | split 460-1597 |
| utterance | 193 | 223 | 241 | 272 | 218 | split 321-562 | split 435-1499 |

Result: max stable 350ms B=224 for both. 200ms B<=64. 100ms not met. B>=320 splits cause tails; admission/formation issue.

## Phase 2 WS result

Real `/ws/tts` on local T4, refHD voice, same 18 s text:

| Mode | First byte | Audio | Chunks | Cap hit |
| --- | ---: | ---: | ---: | ---: |
| `sentence` | 247.42 ms | 18.16 s | 3 | 0 |
| `utterance` | 180.57 ms | 17.28 s | 1 | 0 |

Fixes before pass: `logging` import, cap_hit attribution for mode stream, WS send deadlock via sender task. WAVs in `Code/probes/out/ws_quality/`.

## Listening gate

The owner listened to the fixed B=64 WAVs in
`Code/probes/out/natural_stream/`. The `utterance` and `sentence` WAVs match in
quality. The owner reported no meaningful difference.

Decision:

- Use `sentence` as the default quality mode. It gives the same quality by ear
  and has lower first-frame time in the Phase 0 data.
- Keep `utterance` as the low-load fallback. It is useful for one short
  utterance and for comparison.
- Keep `latency` for extreme load only. It is not a quality mode.
- This is a listening result, not a B result. Phase 2 must prove the 350 ms gate
  at B=224 and B=448.

## Phases

Phase 0: Measure three text policies on a real T4. No server change. DONE.
Phase 1: Add `ARSENAL_CALL_STREAM_MODE` to the server. Add `utterance` and
`sentence`. Use `sentence` as the default. Turn off pause compression and join
in these modes.
Phase 2: Run burst and Poisson ramps at 350, 200, 100 ms. Record max B.
Phase 3: Listen to seams. If sentence seams pass, keep them. If not, use
`utterance` for low load.
Phase 4: Add continuous admission if the tail wait is above the gate.
Phase 5: Make the winner the default. Keep the other modes as env options.

## Non-goals

- No model weight change.
- No second model copy.
- No claim of 100 ms at B=224.
- No quality mode with pause compression.

## Phase 4 finding

`20261122-192327-RUN` tested the cap at 640 with a forced `window=5` ms. It did
not remove the split. A 2 to 4 row early batch formed first. The rest of the
rows then waited for that small batch.

- `sentence` B=224 split into [3, 221] and p95 378 to 482 ms.
- `sentence` B=320 split into [2, 318] and p95 452 to 562 ms.
- `utterance` B=320 was one 320 row batch in 2 of 3 warm reps at p95 266 and
  308 ms. The third rep split and gave p95 685 ms.

So the cap is necessary but not enough. The split is a batch formation problem.
The main cause is a short dispatch window against a large arrival spread.

Next step: test the default window and the `call_first` quiet grace. Look for a
policy that gives one batch at B=320 and B=448. Then wire that policy. Do not
rewrite `BatchedStream` for this step.

## Phase 4 formation review

`20261122-193729-RUN` tested 4 policies in an in-process server. Cap 640.

- `default` (window 150, no quiet): one batch at every B for both modes. Warm
  p95 was 379 to 407 ms at B=320 and 483 to 514 ms at B=448.
- `q2h20` and `q3h40`: split in most warm rows.
- `q2h30`: one batch for `utterance` B=320 at p95 272 and 283 ms. `sentence`
  B=320 split `[1, 319]` at p95 455 and 466 ms.
- No policy gave one batch in every warm row under 350 ms at B=448.

The run report winner check used ANY warm row. Do not read that list as a
robust win. The in-process p95 is not a real-server gate. Assumption A-50 is
unconfirmed.

Next step: a separate-process uvicorn probe with the default window and cap 640.
Measure `sentence` and `utterance` at B=224, 320, 448. This decides if Phase 4 is
a cap change or a model floor. Do not wire a quiet policy yet.

## Phase 4 confirmation

`20261122-195007-RUN` confirms on a separate-process server with the default
window and cap 640. B=320 formed one batch in all warm rows for both modes. The
split is gone. The 350 ms gate is not met at B=320.

Warm p95:

| B | sentence | utterance |
| ---: | ---: | ---: |
| 224 | 316 to 321 ms | 341 to 386 ms |
| 320 | 389 to 413 ms | 421 to 424 ms |
| 448 | 501 to 523 ms | 524 to 715 ms |

The first-byte time includes the full 150 ms window wait. `BATCH_TARGET` was
640, so B<640 never reached the target and the collector waited the full window.
This wait is a large part of the B=320 time.

Next step: test a quiet policy with buckets off at B=320. This removes the
target wait. If no policy passes, report the floor and lock the 350 ms operating
point at B=224 `sentence`.

## Phase 4 quiet formation

`20261122-195737-RUN` tested B=320 with 4 policies and buckets off. No policy
passed. Quiet policies still split `[1,319]`. Cause:
`_collect_call_first_quiet` breaks when `len(batch) >= active_call_sessions`.
This dispatches a 1-row batch before quiet or hard cap.

Next step: guard the early break with a minimum batch size. Re-test B=320 on a
real server.

## Phase 4 quiet fix

`20261122-200804-RUN` added `ARSENAL_CALL_FIRST_MIN_EARLY=32`. The `[1,319]`
split was removed. Small early splits remain (`[2-6,...]`). No policy met 350 ms
on all warm B=320 rows. Some utterance `[320]` rows were 260-317 ms, not
consistent.

Conclusion: B=320 warm p95 <= 350 ms is not stable on one T4 with current
admission. Accept B=224 `sentence` as the 350 ms operating point (FACT-0154:
316-321 ms). B=224 `utterance` is borderline (341-386 ms). Further gain needs
arrival-shape control or client pre-connect, not more collector tuning.

## Phase 5 WS gate (deviated attempt)

`20261122-210000-RUN` measured the real WS path with `sentence` at the default config.
Table: {"224": {"p50": 418.1312417500749, "p95": 2384.7730940001384, "errors": 0}, "320": {"p50": 535.9340824999208, "p95": 4413.444264000191, "errors": 0}}.

Decision: if B=224 `errors` is 0 and `p95` <= 350 ms, B=224 `sentence` is the
locked operating point. If not, inspect the client send and server phase gaps.

B=320 stays a measurement point. Do not set it as a target without a new
formation or admission change.

## Phase 5 WS gate (corrected)

`20261122-230000-RUN` is the valid attempt. It uses a dedicated client with
no `cancel` and no `drain`, and SHA-256 bound output. Attempts 1 and 2 are not used.
Table: {224: {'p50': 414.7405924998111, 'p95': 469.5137859998795, 'errors': 0}, 320: {'p50': 523.107804999654, 'p95': 587.0288289997916, 'errors': 0}}.

Decision: B=224 sentence is not yet locked. Inspect the phase gap.

B=320 stays a measurement point. Do not set it as a target without a new
formation or admission change.

## Phase 5 WS low-latency gate

`20261123-000000-RUN` ran the real WS path with cap 640, target 640,
`max_frames=8`, quiet 50, hard cap 300, and grace 20. It tests `sentence`
only. `utterance` is not used because it OOMs at B=224 on T4.

Table: {224: {'p50': 353.72772549999354, 'p95': 400.70901600029174, 'errors': 0}, 320: {'p50': 499.48913549997087, 'p95': 578.8367110008039, 'errors': 0}, 384: {'p50': 595.9077425000032, 'p95': 670.0646890003554, 'errors': 0}}

Decision: B=320 gate `False`, max B under 350 ms `None`.

Both modes stay in the app. Mode and frame cap are per-request payload
fields. This gate does not change app code.

The low-latency config still fails. Inspect formation and frame count.

## Decision: sentence mode for WS

`20261122-232457-RUN` recorded the B thresholds and the first-chunk cause.

The owner chose `sentence` mode with the current about-40-frame first chunk
for WS going forward. All three modes stay in the app. They are selectable
from the API payload. No app code change is part of this decision.

Default voice, first sound only: 100 ms at B=44, 200 ms at B=96, 300 ms at
B=160. Conditioned voice `v1`: 100 ms at B=48, 200 ms at B=128, 300 ms at
B=192, 350 ms at B=256. B=320 is 437.09 ms with conditioned voice and 578.84 ms
with default voice. The old B=320 at 343.2 ms used an 8-frame first chunk in
an older server revision. That path is not in the current `sentence` mode.

Raw data: `Code/probes/out/ws_burst_gate/sweep_20261122-232457.json`.

Each frame is 80 ms of audio. The old 8-frame first chunk was 0.64 s. The
current about-40-frame first chunk is about 3.2 s.
