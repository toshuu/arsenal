---
id: IDEA-0007
title: Dual service classes - call mode (WebSocket) and normal HTTP on one engine
status: SKELETONIZED
priority: P0
created_in: .stageset/sessions/coding-modal-t4-deploy.md
updated_in: .stageset/sessions/plan-call-mode.md
updated_at: 2026-11-20T15:30:00+05:30
related_ideas: [IDEA-0005]
related_skeletons:
  - Skeletons/Code/batch/job_classes.py
  - Skeletons/Code/batch/call_chunker.py
  - Skeletons/Code/batch/server.py
  - Skeletons/Probes/probe_call_ceiling.md
  - Skeletons/Probes/probe_call_mode.md
related_reports: [.stageset/runs/20261120-142010-RUN.md]
---

# Dual service classes - call mode and normal HTTP

## Goal

Use one engine and one GPU worker for two service classes.

- Normal mode: keep the current HTTP behavior (`/tts`, `/tts/stream`, `/tts/batch`). Playground use. Latency is less important.
- Call mode: WebSocket voice calls. Primary metric: max concurrent call starts B with first-chunk p95 <= 350 ms. Then zero underruns and gap-free continuation.

Owner decision: a short first chunk is correct for voice calls. The user listens to the first sound while later audio generates. Normal HTTP stays available.

Owner decision: keep both modes. Call mode is for high B and low first-sound latency. Normal HTTP is for the playground.

## Does first-chunk-only raise B?

Yes. B goes up a lot. It is not unlimited.

Why:

- Memory and batch time grow with `max_frames`. A first chunk uses 24 to 48 frames, not 192.
- The metric is time to first audio, not time to finish the text. Later chunks do not count for the gate.
- Direct model first emit at B=224 was 97.7 ms (FACT-0111) with a long `max_frames`. A short first chunk must be faster.

What limits B at tight gates:

- Batch window. Waiting to fill a batch adds directly to p95. At a 100 ms gate the window must be near 5 ms.
- Queue behind a running batch. A first chunk that arrives mid-batch waits for the batch to end.
- CPU ingress and chunking on 4 to 8 vCPU. This is the likely wall, not the GPU.
- Continuation load. Many streams need their second chunk at the same time. Priority helps. Watch underruns.

Expected B on T4. These are estimates. The probe must measure them.

| Gate | Expected max B | Limiter |
| --- | ---: | --- |
| first-chunk p95 <= 350 ms | 400 to 1024+ | CPU ingress and chunking |
| first-chunk p95 <= 200 ms | 224 to 400 | CPU plus batch fill |
| first-chunk p95 <= 100 ms | 100 to 224 | batch step and queue |

Phase 0 probe measures this before any code. Do not treat the table as a fact.

## Constraints

- No model-internal change. No second worker. No CUDA graph.
- T4 memory risk at high `max_frames`. Call first frames are small (24 to 48).
- Batches are never mixed across classes.
- Test in-container on T4 with no public proxy. Stop the GPU after tests.
- Normal HTTP behavior does not change.
- Compare all runs to equal runs. Record env and arrival mode.

## Design

1. Job classes: `call_first`, `call_cont`, `normal`. Separate queue per class. One batch at a time. Priority `call_first > call_cont > normal`. Lower integer = higher priority.
2. Per-class settings from env:
   - `ARSENAL_CALL_FIRST_MAX_FRAMES` default 32. Sweep 24, 32, 48.
   - `ARSENAL_CALL_FIRST_MAX_BATCH` default 224.
   - `ARSENAL_CALL_CONT_MAX_FRAMES` default 192.
   - `ARSENAL_CALL_CONT_MAX_BATCH` default 224.
   - `ARSENAL_NORMAL_MAX_FRAMES` default 192.
   - `ARSENAL_NORMAL_MAX_BATCH` default 192.
   - `ARSENAL_NORMAL_BUSY_MAX_BATCH` default 32.
   - `ARSENAL_NORMAL_BUSY_MAX_FRAMES` default 64.
   - `ARSENAL_BATCH_WINDOW_MS` default 150. Per-class window is allowed.
3. Head-of-line bound: when any call session is active, normal uses the busy caps. Report the max wait of a `call_first` job behind a normal batch as `call_first_wait_behind_normal_ms`.
4. Chunking for call mode: first chunk is the first clause, 4 to 8 words, cap about 2 s of audio. Later chunks are longer. Split at punctuation. All chunks use the same voice conditioning. Cache `chunks_for` by `(text, mode)`. Batch tokenization. Target `handler_to_chunks_done < 30 ms` at B=224.
5. WebSocket `/ws/tts`:
   - Client messages: `start{voice, mode}`, `text{text}`, `flush`, `cancel`.
   - Server messages: binary PCM frames plus JSON events `chunk_start`, `chunk_done`, `error`.
   - Cancel drops queued jobs and frees rows.
6. HTTP is unchanged. Optional `?mode=call` on `/tts/stream` routes to the call class for playground use.

## Phases

Phase 0. Probe the ceiling. Use the existing in-container selfprobe with `max_frames` 24, 32, 48. Ramp B 224 to 1024, burst and Poisson. Measure first-chunk p95, peak VRAM, errors. Save a run report. This answers the B question before code. Harness may need a small `max_frames`-per-job change. That change is part of `server.py` revision 10.

Phase 1. Implement `job_classes.py` and `call_chunker.py`. Add checks.
Phase 2. Update `server.py` to revision 10. Add `/ws/tts`, class routing, head-of-line bound, metrics. Normal HTTP checks must still pass.
Phase 3. Run `probe_call_mode.md` on T4 in-container:
- Ramp B = 224, 320, 448, 512, 640, 768, 1024. Stop at the first failure. Burst and Poisson at 3 rates.
- Sweep window = 0, 5, 10, 25 ms.
- Sweep first `max_frames` = 24, 32, 48.
- Report max B at each gate: 350, 200, 100 ms.
- Seamless check: 60 s streams at target B. Zero underruns. Report slack p5 and p50.
- Mixed: 128 call streams plus 32 normal HTTP. Report both p95 values.
- Cancel: cancel 50 percent mid-stream. VRAM flat. Queues empty.
- Save 5 joined call-mode streams for listening.
Phase 4. Record facts and a run report. Stop the app.

## Acceptance gates

| Gate | Pass condition |
| --- | --- |
| Call first chunk, 350 ms | max B with p95 <= 350 ms, 0 errors |
| Call first chunk, 200 ms | max B with p95 <= 200 ms, 0 errors |
| Call first chunk, 100 ms | max B with p95 <= 100 ms, 0 errors |
| Seamless | 0 underruns over 60 s at target B, slack p5 >= 0 ms |
| Normal regression | server p95 at B=32 and B=64 within 10 percent of baseline |
| Cancel | no VRAM growth, queue depth 0 after 10 s |
| Memory | peak VRAM below the T4 safe limit, no OOM |

## Stop rules

- Stop the ramp at the first failure. Do not tune env values mid-ramp.
- If a normal batch blocks `call_first` above 350 ms, write a READY preemption plan only. Do not code preemption without owner approval.
- If peak VRAM is within 1 GiB of the limit, reduce first `max_frames` before you raise B.
- If the first-chunk floor is above 100 ms at B=224, report the floor. Do not claim the 100 ms gate.
- Do not compare runs with different client limits or arrival modes.

## Non-goals

- No model-internal change.
- No second worker or second model copy.
- No CUDA graph.
- No change to normal HTTP defaults.

## Report fields

`mode | class | B | arrival | window_ms | first_max_frames | peak VRAM MB | first-chunk p95 ms | underruns | slack p5 ms | normal p95 ms (mixed) | errors`
