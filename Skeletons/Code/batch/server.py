<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/server.py
@stageset source_idea: IDEA-0005
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 12
@stageset implemented_revision: 12
@stageset planned_in: .stageset/sessions/coding-latency-onset-fix.md
@stageset last_updated_in: .stageset/sessions/coding-latency-onset-fix.md
@stageset implemented_in: .stageset/sessions/coding-latency-onset-fix.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: HTTP serving layer

## Purpose

Serve one bounded batch worker over HTTP. Reject overload. Cancel queued work.
Report health and metrics.

## Contract

- `POST /tts` takes `{text, max_frames?, voice_profile?}` and returns `audio/wav`.
- `POST /tts/batch` takes `{texts, max_frames?, voice_profile?}` and returns a JSON list of base64 WAV items.
- `POST /tts/stream` takes the same body as `/tts` and returns raw 16-bit PCM (`audio/L16`) as chunks arrive.
- `/metrics` reports p50/p95/max for queue, first chunk, and total time.
- Without `voice_profile`, the server uses the reference voice clip on the normal path.
- With `voice_profile`, the server loads that id from `ARSENAL_VOICE_PROFILES`.
- Mixed profile ids in one call use the normal path with per-row voice tensors.
- Each text is submitted one chunk at a time. First chunks batch before continuations.
- The worker drains all waiting jobs before it uses the time window.
- The time window is `ARSENAL_BATCH_WINDOW_MS` (default 150 ms) and the low-load fill target is `ARSENAL_BATCH_TARGET` (default 32 jobs).
- `GET /health` returns readiness, queue depth, and counters.
- The queue is bounded by `ARSENAL_MAX_QUEUE` (default 256).
- The worker takes at most `ARSENAL_MAX_BATCH` jobs per call (default 224).
- One call has at most `ARSENAL_MAX_ROWS` texts (default 224).
- Boot runs prewarm B=192, 1 frame, unless `ARSENAL_PREWARM=0`.
- A `max_frames` above `ARSENAL_MAX_FRAMES` returns 413 before submit.
- A full queue returns 503. An empty text returns 422. A long text returns 413.
- A request above `ARSENAL_TIMEOUT_S` returns 504.
- A stream sends the first PCM chunk before generation ends. A client disconnect stops the job.
- Frames over the safe limit return 413. A long text that cannot fit the frame budget returns 413.
- A client disconnect sets the job stop event and drops queued work.
- An unknown `voice_profile` returns 400.
- A profile call with mixed first-chunk token lengths uses the normal voice path.
- A batch with one profile id uses the conditioned path. A batch with mixed profile ids uses the normal path with per-row voices.
- Per-row voice prefill uses one batched text conditioner call, not one call per row.
- Text chunk results are cached per text.
- `request_first_chunk_ms` in `/metrics` counts only the first chunk of each request.
- Each job has `job_class`: `call_first`, `call_cont`, or `normal`. Normal HTTP jobs are `normal`.
- The worker uses `job_classes.select_batch`. One batch never mixes classes.
- Priority is `call_first > call_cont > normal`.
- While any call session is active, normal batches use `ARSENAL_NORMAL_BUSY_MAX_BATCH` and `ARSENAL_NORMAL_BUSY_MAX_FRAMES`.
- `call_first` jobs use `ARSENAL_CALL_FIRST_MAX_FRAMES` (default 32). `call_cont` jobs use `ARSENAL_CALL_CONT_MAX_FRAMES` (default 192).
- `GET /ws/tts` is a WebSocket. Client sends `start{voice?, mode?}`, `text{text}`, `flush`, `cancel`.
- The call stream sends binary 16-bit PCM frames and JSON events `chunk_start`, `chunk_done`, `error`.
- Call chunks use `call_chunker.split_call_text`: short first chunk, then longer chunks, same voice.
- `?mode=call` on `/tts/stream` routes the request to `call_first` and `call_cont`.
- `/metrics` adds `first_chunk_ms` per class, `call_first_wait_behind_normal_ms`, `active_call_sessions`, and `underruns`.
- A WS `start` may set `stream_mode` or `mode` to `sentence`, `utterance`, or `latency`. Default is `ARSENAL_CALL_STREAM_MODE` or `sentence`.
- `sentence` uses no first-token cut, 224 frame budget, and 50-token text chunks.
- `utterance` uses no first-token cut, 512 frame budget, and one job for the whole text.
- `latency` keeps the legacy 16-token first cut and 192 frame budget.
- Quality modes skip pause compression. `latency` keeps it.
- In `latency` mode the first PCM frame is sent raw before the pause compressor starts. Later frames on that chunk still use the compressor.
- `sentence` and `utterance` send raw frames on every chunk. This is unchanged.
- `chunk_start` and `utterance_done` include `stream_mode`.
- A normal HTTP request never changes class and never uses a call-mode chunker.
- A cancel frees queued jobs and sets the stop event. Rows are released at the batch end.
- The WebSocket closes after `flush` completes all chunks, or on `cancel`, or on client close.
- When `ARSENAL_DEBUG=1`, these read-only debug routes exist for the probes:
  `/debug/callramp`, `/debug/callmixed`, `/debug/callcancel`, `/debug/vram`.
  They call the same WebSocket path as a real client. They do not change project files.

## Edge cases

- Engine not ready: `/health` returns 503.
- One failed batch: every job in that batch gets the error. The worker stays alive.
- More than one job in a batch: jobs with the same profile id are flattened, synthesized once, then split back by job.
- Disconnect during generation: the result is discarded. The current batch is not split.

## Checks

### CHECK-SERVER-01 - serving behavior

- Command: `python Code/probes/check_server.py`
- Predicted output: `{"ok": true}`
- Pass condition: exit code 0 and `ok` is true.
- Fail condition: any other output or a non-zero exit code.

### CHECK-SERVER-02 - real engine WAV

- Command: `PYTHONPATH=/kaggle/working/pocket-tts python -m uvicorn batch.server:app`
- Predicted output: `/health` returns 200 after load, and `POST /tts` returns 200 with `audio/wav`.
- Pass condition: a run report shows `/health` 200, default `/tts` 200 with `audio/wav`, profile `/tts` 200 with `audio/wav`, and unknown profile 400.
- Fail condition: readiness is false, the WAV response is empty, or the profile select fails.

### CHECK-SERVER-08 - HTTP load

- Command: `python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, ...}`
- Pass condition: first-chunk p95 <= 350 ms, RTF < 1.0, 0 errors.
- Fail condition: p95 above 350 ms, RTF at or above 1.0, or any non-200 response.

### CHECK-SERVER-10 - 32-client gate

- Command: `ARSENAL_LOAD_BURSTS=5 ARSENAL_LOAD_PER_BURST=32 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 160, "p95": <= 350}`
- Pass condition: client p95 <= 350 ms, 0 errors, RTF < 1.0. Use the saved JSON.
- Fail condition: client p95 above 350 ms, any error, or RTF at or above 1.0.

### CHECK-SERVER-11 - 224-client single-profile gate

- Command: `ARSENAL_LOAD_LIMITS=256 ARSENAL_LOAD_SINGLE_PROFILE=v1 ARSENAL_MAX_BATCH=224 ARSENAL_MAX_ROWS=224 ARSENAL_BATCH_TARGET=224 ARSENAL_BATCH_WINDOW_MS=700 ARSENAL_LOAD_BURSTS=2 ARSENAL_LOAD_PER_BURST=224 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 448, "p95": <= 350}`
- Pass condition: client p95 <= 350 ms, 0 errors, RTF < 1.0.
- Fail condition: client p95 above 350 ms, any error, or RTF at or above 1.0.

### CHECK-SERVER-04 - first-chunk streaming

- Command: `curl /tts/stream` with a long text, then `curl /metrics`.
- Predicted output: status 200, TTFB far below total time, and `first_chunk_ms.count` above zero.
- Pass condition: a run report shows TTFB below 350 ms and full time above TTFB.
- Fail condition: the stream waits for the full audio, or metrics have no first-chunk samples.

### CHECK-SERVER-03 - profile image wiring

- Command: `python Code/batch/build_voice_profiles.py OUT_DIR id=voice.wav`
- Predicted output: `PROFILE id OUT_DIR/id.pt`.
- Pass condition: the run report shows the file exists and a server started with `ARSENAL_VOICE_PROFILES=id=OUT_DIR/id.pt` serves a profile request with 200.
- Fail condition: the build fails or the server cannot load the id.

### CHECK-SERVER-12 - WS mode helper

- Command: `python Code/probes/check_server_modes.py`
- Predicted output: `{"ok": true}`
- Pass condition: exit code 0 and mode resolution, mode settings, and raw-frame flag are correct.
- Fail condition: unknown mode accepted, wrong settings, or compression enabled for a quality mode.

### CHECK-SERVER-13 - latency first frame not held by compressor

- Command: `python /tmp/opencode/mode_stage_ab.py`
- Predicted output: latency `ws_after_emit_ms` max below 50 ms and latency client p95 within 25 ms of sentence p95 on one server at B=48.
- Pass condition: both values hold and both modes have 0 errors.
- Fail condition: latency first-emit-to-byte max at or above 50 ms, or latency p95 more than 25 ms above sentence p95.

### CHECK-CALL-WS-01 - WebSocket call stream

- Command: start the server, open `/ws/tts`, send `start{}`, `text{"Hello there, this is a call."}`, `flush`, read messages.
- Predicted output: one or more binary PCM frames, then JSON `chunk_done` and a final close.
- Pass condition: a run report shows at least one binary frame, a `chunk_done` event, and exit code 0.
- Fail condition: no binary frame, no `chunk_done`, or an unhandled exception.

### CHECK-CALL-NORMAL-01 - normal HTTP not regressed

- Command: `ARSENAL_LOAD_BURSTS=5 ARSENAL_LOAD_PER_BURST=32 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py`
- Predicted output: `{"ok": true, "requests": 160, "p95": <= 350}`
- Pass condition: server first-chunk p95 within 10 percent of FACT-0110 (294.0 ms), 0 errors.
- Fail condition: server p95 above 323.4 ms, any error, or a changed response body.

### CHECK-CALL-HOL-01 - call first chunk not blocked by normal

- Command: `arsenal_call_mixed` mode in `probe_call_mode.md`: 128 call streams plus 32 normal HTTP.
- Predicted output: call first-chunk p95 <= 350 ms and normal p95 recorded separately.
- Pass condition: call p95 <= 350 ms and `call_first_wait_behind_normal_ms` p95 <= 350 ms.
- Fail condition: call p95 above 350 ms. Then write a READY preemption plan only.

### CHECK-CALL-CANCEL-01 - cancel frees work

- Command: the cancel test in `probe_call_mode.md`: cancel 50 percent of streams mid-stream.
- Predicted output: after 10 s, `active_call_sessions` is 0, queue depth is 0, and VRAM is flat.
- Pass condition: queue depth 0, no error, VRAM change under 100 MB.
- Fail condition: a stuck session, a growing queue, or VRAM growth.

## References

- `Ideas/IDEA-0005-long-text-and-production-readiness.md`
- `Ideas/IDEA-0007-dual-service-call-mode.md`
- `Skeletons/Code/batch/job_classes.py`
- `Skeletons/Code/batch/call_chunker.py`
- `Skeletons/Probes/probe_call_mode.md`
- `Code/batch/batched_stream.py`
- `Code/probes/check_server.py`
- `Code/batch/build_voice_profiles.py`
- `Code/batch/VOICE_PROFILES.md`
- `.stageset/runs/20261119-191119-RUN-04.md`
