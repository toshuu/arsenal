---
type: CODING
time: 2026-11-20T13:25:14+05:30
summary: Deploy Arsenal TTS on a Modal T4, add a co-located prober and direct bench, and stop the GPU after the test.
paths: Code/deploy/modal_app.py; Code/batch/server.py; Code/probes/probe_http_load.py; .stageset/facts.md; .stageset/runs/20261120-132514-RUN.md
related: IDEA-0005; SSLD-017; 20261120-132514-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use one Modal T4 app named `arsenal-tts-t4` for serving.
- Use a separate app named `arsenal-tts-dev` for helpers. `modal run` stops the
  app that owns the function. A shared name stops the deployment.
- Store the voice cache and profiles in the `arsenal-tts-cache` Volume.
- Keep `scaledown_window=60`, `min_containers=0`, and `max_containers=1`.
  Stop the app with `modal app stop arsenal-tts-t4 -y` after a test.
- Add a remote mode to `probe_http_load.py` with `ARSENAL_LOAD_BASE`.
- Add `chunk_ms`, `batch_size`, `batch_spread_ms`, and `batch_wait_ms` metrics.
- Use a 64-thread chunk pool for `chunks_for`.

## Outcomes

- The Modal T4 app serves real audio. Cold `/health` is 17.3 s.
- Direct B=32 first emit is 33.7 to 45.3 ms. The model path is fast.
- The external 32-client gate fails: client p95 2151 ms.
- Server batch spread p95 is 1380 ms. Batch size p50 is 14. Small batches run
  serially. Late jobs wait for the prior batch. Chunk time is not the cause.
- The public URL adds about 188 ms per request from this Kaggle host.
- The GPU is stopped. No containers remain.

## Follow-up

- Plan continuous batching, or accept the network floor.
- Run the prober inside the serve container for a no-proxy server gate.
- Do not treat the Modal HTTP gate as passed.
