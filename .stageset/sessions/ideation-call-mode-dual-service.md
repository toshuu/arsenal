---
type: IDEATION
time: 2026-11-20T14:20:10+05:30
summary: Record dual service class plan (call/WebSocket + normal HTTP) and T4 diagnosis evidence.
paths: Ideas/IDEA-0007-dual-service-call-mode.md; Ideas/_index.md; .stageset/facts.md; .stageset/runs/20261120-142010-RUN.md
related: IDEA-0005; IDEA-0007; FACT-0123; FACT-0124; FACT-0125; FACT-0126; 20261120-142010-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep one engine/worker/model. Add two service classes: `call_first`, `call_cont`, `normal`.
- Call mode over WebSocket for voice-call TTFA; normal HTTP unchanged. Optional HTTP `?mode=call`.
- No model-internal change, no second worker, no CUDA graph.
- Short first chunk accepted for call UX; measure seamless continuation.

## Outcomes

- Added IDEA-0007 with scheduler, chunking, WS protocol, limits, tests, and report fields.
- Added run 20261120-142010-RUN and FACT-0123..0126: ingress not 7 s; T4 B=224 OOM at mf192; mf160/128 fit 1 burst; sustained mf160 B=224 p95 1262 ms; chunking and `cond_to_flow0` grow at high B.
- Modal GPU stopped after tests.

## Follow-up

- Implement per-class queues/scheduler, call chunker, `/ws/tts`, and in-container tests per IDEA-0007.
- If call blocked by normal batch >350 ms, write READY preemption plan (approval required).
- Consider L4 for mf192 sustained B=224.
