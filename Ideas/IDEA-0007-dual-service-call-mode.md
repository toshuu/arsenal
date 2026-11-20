---
id: IDEA-0007
title: Dual service classes - call mode (WebSocket) and normal HTTP on one engine
status: DISCOVERY
priority: P0
created_in: .stageset/sessions/coding-modal-t4-deploy.md
updated_in: .stageset/sessions/ideation-call-mode-dual-service.md
updated_at: 2026-11-20T14:20:10+05:30
related_ideas: [IDEA-0005]
related_skeletons: [Skeletons/Code/batch/server.py]
related_reports: [.stageset/runs/20261120-142010-RUN.md]
---

# Dual service classes - call mode and normal HTTP

## Goal

One engine, one GPU worker/model. Two service classes.
- Normal mode: keep current HTTP behavior (`/tts`, `/tts/stream`, `/tts/batch`).
- Call mode: WebSocket for AI voice calls. Metric: first-chunk p95 <= 350 ms at max concurrent call starts B, then gap-free continuation. Short first chunk is OK.

Owner note: short first chunk is acceptable for voice calls (user listens while later audio generates). Optional `?mode=call` on HTTP stream for playground use.

## Constraints

- No model-internal change. No second worker. No CUDA graph.
- T4 memory risk at high `max_frames`; call first frames small (24-48).
- Test in-container on T4 (no public proxy). Stop GPU after tests.

## Proposed design

1. Job classes: `call_first`, `call_cont`, `normal`. One batch at a time, no mixed-class batch. Priority `call_first > call_cont > normal`.
2. Per-class env: `ARSENAL_CALL_FIRST_MAX_FRAMES` (default 32, sweep 24/32/48), `ARSENAL_CALL_CONT_MAX_FRAMES`, `ARSENAL_NORMAL_*`. Keep normal defaults.
3. Head-of-line bound: when call sessions active, cap normal with `ARSENAL_NORMAL_BUSY_MAX_BATCH`, `ARSENAL_NORMAL_BUSY_MAX_FRAMES`. Report max wait of `call_first` behind normal.
4. Chunking: call first chunk 4-8 words (~2 s max), split at clause/punctuation; longer continuations, same voice. Cache `chunks_for` by `(text,profile,mode)`, batch tokenization. Target `handler_to_chunks_done < 30 ms` at B=224.
5. WebSocket `/ws/tts`: client `start|text|flush|cancel`, server binary PCM + JSON `chunk_start|done|error`. Cancel drops queued jobs and frees rows.
6. HTTP unchanged. Optional `?mode=call` on `/tts/stream`. Normal regression B=32/64 within 10%.

## Tests (in-container)

- Call ramp B=224,288,384,512, burst and Poisson: first-chunk p95, peak VRAM, batch wall, errors.
- Seamless: `t_first_byte(chunk N+1) - playback_end(chunk N)`; underruns, slack p5/p50, target 0.
- Mixed: 128 call + 32 normal HTTP; report call first-chunk p95 and normal p95.
- Cancel: 50% mid-stream; VRAM flat, queues empty.
- Save 5 joined call-mode samples.

## Open / risk

- Seam quality at chunk joins needs listening.
- First-chunk `max_frames` needs sweep (24/32/48).
- If `call_first` wait > 350 ms due to normal batch: READY plan only, preempt normal at chunk boundary (owner approval).
- Sustained B=224 on T4 is not yet stable at 350 ms (FACT-0125); call-first small frames may help memory/latency but must be measured.

## Report fields

`mode | B | arrival | first_max_frames | peak VRAM MB | first-chunk p95 ms | underruns | slack p5 ms | normal p95 ms (mixed)`
