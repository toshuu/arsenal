---
id: IDEA-0005
title: Long-text correctness and production readiness gaps
status: DISCOVERY
priority: P0
created_in: .stageset/sessions/coding-production-readiness-fixes.md
created_at: 2026-11-18
updated_in: .stageset/sessions/ideation-production-validation-plan.md
updated_at: 2026-11-19
related_ideas: [IDEA-0001, IDEA-0003, IDEA-0004]
related_skeletons: [Skeletons/Code/batch/batched_stream.py, Skeletons/Code/batch/server.py]
related_reports: []
---

# Long-text correctness and production readiness gaps

**Purpose:** Independent review proposal based on the current `main` branch. This is not an implementation request. The Arsenal agent and other reviewers must verify each finding against current code, tests, and StageSet facts before creating or changing a Skeleton.

**Review rule:** Do not accept a claim in this document only because it is written here. Re-check the referenced code and run the proposed tests. If the code has changed, update or reject the finding.

## 1. Executive summary

The repository has demonstrated strong short-request burst performance on one T4. The remaining risks are not basic audio streaming. They are:

1. **Full-input text correctness:** verify that the server synthesizes every part of the submitted text. The current batch path appears to select only the first text segment.
2. **Long-generation safety and continuation:** the current frame limit prevents unsafe allocation, but the stream loop does not appear to continue generation after reaching the limit.
3. **Production deployment:** the Modal plan is documented, but the StageSet facts still mark the build as not started.
4. **L4 validation:** the T4 result does not establish L4 capacity. The planned L4 benchmark is still open.
5. **Operational behavior:** verify request admission, overload behavior, cold start, and voice-cache setup in the actual deployment.

Do not treat these as proven defects until the verification steps below pass.

## 2. Finding A — Verify that the complete input text is synthesized

**Priority:** P0  
**Status:** Code-level concern; requires a focused correctness test.

### Evidence in current code

In `Code/batch/batched_stream.py`:

- `_first_chunk_text()` calls `split_into_best_sentences(...)`.
- It then assigns `first = chunks[0] if chunks else text`.
- `_text_ids()` encodes that `first` value.
- When `max_first_tokens` is not set, `_first_chunk_text()` still returns only `chunks[0]`.
- `stream()` performs one conditioning pass, then one generation loop. It does not visibly iterate over the remaining text segments.

This means the batch path may synthesize only the first segment of a multi-sentence input. Audio is emitted frame by frame, but that does not prove that all submitted text is consumed.

### Required verification

1. Pass a text with three clearly distinct sentences.
2. Record the exact text segments returned by `split_into_best_sentences()`.
3. Record the token IDs actually passed into conditioning.
4. Generate audio and use a reliable transcription or a controlled phrase test to verify that sentence 1, 2, and 3 are all present.
5. Repeat with:
   - one sentence below the token limit;
   - one sentence above the token limit;
   - multiple short sentences;
   - mixed-language text;
   - punctuation and abbreviations.
6. Check the normal server/API entry point as well as direct `BatchedStream.stream()` calls. Do not infer server behavior from the batch class alone.

### Possible required change — only if the tests confirm the issue

Implement full-text segmentation and sequential generation. Each segment must produce audio in order. The implementation must define whether the model state, codec state, EOS state, and voice conditioning are carried or reinitialized between segments.

Do not assume that concatenating independently generated segments is equivalent to continuous generation. Test joins for pauses, clicks, prosody, voice consistency, and missing or duplicated words.

### Acceptance criteria

- The API synthesizes the complete input, or it rejects input that exceeds a clearly documented limit. It must not silently omit text.
- The output order matches the input order.
- No segment is silently skipped or duplicated.
- Audio joins pass listening and objective checks.
- Existing short-text quality and TTFA do not regress beyond an agreed threshold.

## 3. Finding B — Long-text continuation beyond the frame limit

**Priority:** P1  
**Status:** Limit and guard are documented; continuation is not evidenced.

### Evidence in StageSet

The current facts record:

- `FACT-0079`: B=224 with `max_frames=300` and long text caused an OOM during Mimi state initialization.
- `FACT-0080`: state memory grows with `max_frames`; there is no sliding window in the measured path.
- `FACT-0081`: the safe B=224 limit is approximately 192 frames, with at least 1.5 GiB free.
- `FACT-0083` and `FACT-0084`: `ARSENAL_MAX_FRAMES` / `max_allowed_frames` rejects an over-limit request before state allocation.
- `FACT-0086`: long-text chunking with carried state remains open.

In `Code/batch/batched_stream.py`, `stream()` allocates flow and Mimi state using `max_frames`, then runs `for step in range(max_frames)`. The loop ends at EOS or when the frame budget is exhausted. No outer continuation loop is visible in this method.

### Required verification

1. Test texts whose estimated generation lengths are below, at, and above the configured frame limit.
2. Confirm whether an over-limit request is rejected, truncated, or continued.
3. Confirm whether EOS is reached before the frame limit for normal long inputs.
4. Measure peak allocated and reserved VRAM at B=224 for representative text lengths.
5. Verify the behavior for mixed-length rows in one batch.

### Possible required change — only if product requirements need longer output

Add bounded sequential segments or another memory-bounded continuation design. Do not increase `max_frames` blindly. The T4 evidence shows that a larger allocation can cause OOM.

Before implementation, decide and document:
- how text is segmented;
- whether model state is carried between segments;
- how Mimi decoder state is handled at segment boundaries;
- how EOS and final-frame handling work;
- how partial audio is delivered to the client;
- how cancellation and errors affect an in-progress multi-segment request.

### Acceptance criteria

- No silent truncation.
- No init-time OOM for requests within the documented input policy.
- Requests outside the policy receive a clear error, unless safe continuation is implemented.
- Audio continuity and text coverage pass tests.
- Memory remains within a measured safety margin at the supported batch size.

## 4. Finding C — Modal deployment is still a plan, not a completed deployment

**Priority:** P0 for serving users  
**Status:** Planned, not built, according to the current deployment document.

### Evidence

`LivingDocs/SSLD-017-modal-deployment-plan.md` begins with `status: PLANNED, not built`. It specifies a single-T4 container, B=224 cap, FP16 decoder weights, voice-cache prebuild, and cold-start measurements.

The document also records a measured boot path of about 6.7 seconds in the current environment. This is not a verified Modal cold-start result.

### Required work

1. Build the Modal image from the documented, pinned model and code versions.
2. Include the FP16 weight artifact and prebuilt voice cache in the image, or document why the cache is created at runtime.
3. Set and verify `ARSENAL_MAX_FRAMES=192` for the B=224 T4 configuration.
4. Verify readiness only after model load, cache load, prewarm, and GPU synchronization.
5. Test a cold container and a warm container.
6. Test B=192 and B=224 under the documented workload.
7. Verify logs, timeouts, cancellation, error responses, and container shutdown.

### Acceptance criteria

- A real Modal deployment exists and can serve a test request.
- Cold-start time and first-request TTFA are measured on Modal.
- Warm p50/p95 TTFA, RTF, peak VRAM, and error count are recorded.
- Over-limit requests are rejected safely.
- The deployed artifact and configuration match the tested commit.

## 5. Finding D — Validate the L4 separately

**Priority:** P1  
**Status:** Planned; no L4 result is established by the T4 measurements.

### Evidence

The current deployment plan lists L4 runs at B=224, 256, and 288. The StageSet facts identify the L4 rerun as open. T4 results must not be presented as L4 results.

### Required work

Run the same pinned code, model, workload, and measurement method on L4. Test B=224, 256, and 288. Include mixed text lengths and repeated bursts.

Record:
- p50, p95, and maximum TTFA;
- steady per-frame time and aggregate RTF;
- peak allocated and reserved VRAM;
- completed, rejected, failed, and timed-out requests;
- cold and warm behavior;
- the maximum safe batch size under the agreed RTF and memory margins.

Do not select the largest batch only because it completes a short soak. Apply the same sustained RTF and safety gates used for T4.

## 6. Finding E — Verify production admission and lifecycle behavior

**Priority:** P1  
**Status:** Needs deployment-level verification.

The T4 benchmark proves a controlled batch result. It does not by itself prove safe behavior when real clients send requests at different times or disconnect.

Verify:

1. What happens when requests arrive while a batch is running.
2. Whether the scheduler has a bounded queue and a maximum queue wait.
3. Whether overload causes a clear rejection or an unbounded wait.
4. Whether a client disconnect cancels work or leaves GPU work running.
5. Whether one failed row affects other rows in the same batch.
6. Whether timeouts cover queue wait and generation time.
7. Whether metrics distinguish accepted, queued, rejected, completed, failed, and cancelled requests.
8. Whether voice-cache misses can occur on the request hot path after deployment.

Do not add a more complex scheduler unless measurements show that the current admission path is inadequate.

## 7. Work order

| Order | Item | Reason | Required output |
|---|---|---|---|
| 1 | Verify complete-text behavior (Finding A) | Possible user-visible text loss | Repro test and code-path report |
| 2 | Verify frame-limit behavior (Finding B) | Possible long-output truncation | Boundary tests and continuation decision |
| 3 | Complete Modal deployment (Finding C) | No production deployment evidence yet | Deployment run report |
| 4 | Run L4 benchmark (Finding D) | Hardware capacity is unknown | L4 benchmark report |
| 5 | Verify lifecycle and admission (Finding E) | Production reliability | Load and failure test report |

The agent can reorder work if current code or newer StageSet evidence changes the priority.

## 8. Explicit non-goals

Do not reopen completed work without new evidence:

- Do not replace the current audio frame streaming path merely because long-text segmentation is open.
- Do not add CUDA graphs by default. Current facts say the attempted Mimi graph path was blocked and the profile was substantially kernel-bound.
- Do not add a second model worker per T4. Current facts show worse latency under two-process GPU sharing.
- Do not raise the T4 B=224 frame limit without a new memory measurement.
- Do not claim that a higher batch size is better unless the RTF and safety gates pass.
- Do not start TensorRT/ONNX work unless the owner approves it or new profiling justifies it.

## 9. Reviewer response format

For each finding, report:

- **VERIFIED**, **PARTLY VERIFIED**, **NOT REPRODUCED**, or **STALE**.
- Exact file and function, or StageSet fact/run, that supports the conclusion.
- A minimal reproduction or test result.
- Whether a new Skeleton is justified.
- Any correction to this document.

Do not implement from this idea file. First verify the findings, resolve conflicts with current StageSet facts, and ask the owner before changing scope.

## 10. Current verification status (2026-11-19)

| Finding | Status | Evidence |
| --- | --- | --- |
| A — full input text | **VERIFIED** | `stream()` splits every text and runs all chunks in order. A 69-token text gave 3 chunks, 0 missing words, 10.8 s of audio. FACT-0088. |
| B — frame limit | **PARTLY VERIFIED** | The guard raises before state allocation. Auto budget comes from the token estimate. Explicit truncation is recorded. Chunk joins and carried state are not tested yet. FACT-0089, FACT-0090. |
| C — Modal | **PLANNED** | No build. Voice cache and profile wiring steps are documented in `LivingDocs/SSLD-017-modal-deployment-plan.md`. |
| D — L4 | **PLANNED** | No L4 result. T4 figures stay T4-only. |
| E — lifecycle | **PARTLY VERIFIED** | Bounded queue, 503 overload, 504 timeout, disconnect stop, and cancel exist. Server now defaults to B=192, 224 rows, queue 256, prewarm on. A real load probe is not run. FACT-0091, FACT-0096, FACT-0097. |

The server now has a first-chunk stream: `/tts/stream` sends raw PCM.
Real engine, 96 frames: TTFB 82.9 ms, total 974.7 ms (FACT-0097).

## 11. Next planned work (owner approved, 2026-11-19)

Do these before L4 and Modal.

### P1 — End-to-end HTTP load probe

- Add `Code/probes/probe_http_load.py`.
- Real engine through HTTP. Many bursts. Mixed profiles and text lengths.
- Measure: queue ms, first-chunk p50/p95/max, total ms, RTF, error rate, 503 count, peak VRAM.
- Pass: p95 first chunk <= 350 ms, sustained RTF < 1.0, zero unexpected errors, no OOM.

### P2 — Long text through HTTP with a profile

- Add `Code/probes/check_long_text_http.py`.
- Use one long multi-sentence text and a profile id. Use `/tts` and `/tts/stream`.
- Verify complete text coverage, chunk count, total audio length, and no missing or repeated words.
- Pass: all chunks present, output order correct, no 5xx.

### P3 — Chunk join and carried-state decision

- Add `Code/probes/check_chunk_joins.py`.
- Measure the join boundaries. Check silence, click, duplicated word, prosody, and voice change.
- Compare independent chunks against one continuous generation where possible.
- Record a decision: keep reconditioning per chunk, or carry state. Update this idea and the batched stream skeleton.

### P4 — Slow-client stream backpressure

- Bound the `/tts/stream` queue or add flow control.
- A slow client must not grow memory without limit.
- Add a probe check: stop reading, then confirm memory stays bounded and the job stops.
- Pass: bounded memory, no worker deadlock, clear cancel behavior.

## 12. Non-goals for this round

- No true mixed-profile GPU batch.
- No true conditioned mixed-length single call. Both need the risky attention change in the permission gate.
- No L4 run.
- No Modal build.

## 13. Results of planned work 1 to 4 (2026-11-19)

| Item | Status | Evidence |
| --- | --- | --- |
| P1 HTTP load probe | **DONE** | `probe_http_load.py`: 160 requests, p50 173.68 ms, p95 226.66 ms, 0 errors, RTF 0.024-0.029. FACT-0103. |
| P2 Long text through HTTP | **DONE** | 4-chunk text with a profile: 664,364-byte WAV and 645,120-byte PCM stream. FACT-0099. |
| P3 Chunk joins | **OBJECTIVE PASS, LISTENER PENDING** | No click, no RMS drop, exact word order. WAVs saved. Owner listening gate still required. FACT-0100. |
| P4 Slow-client backpressure | **DONE** | 64-chunk bound. Full queue stops the job and counts `slow_clients`. FACT-0101. |

The load probe first failed at p95 8641 ms. Fixes: one chunk per job (first chunks batch first), a 100 ms batch window, and per-row voice batching for mixed profiles in the normal path. B=224 with max_frames=192 fits with 1.95 GiB free (FACT-0102).

Carried state is not implemented. Keep independent chunks unless owner listening finds a defect.

## 14. Batch window tuning (2026-11-19)

- A 40 ms window at B=224 gives p95 6047.72 ms over 448 requests. Queue p50 733.84 ms. FAIL (FACT-0105).
- A 180 ms window and first-chunk priority give p95 321.32 ms over 160 requests at 32 clients. PASS (FACT-0106).
- Default `ARSENAL_BATCH_WINDOW_MS` is now 180 ms.
- 224-client bursts need more work. RTF is safe, but TTFA is not.

## 15. Final batch tuning (2026-11-19)

- Target-driven batching is in place. The worker waits for 32 jobs or a 300 ms cap. First chunks have priority.
- Three 32-client runs pass. Client p95: 205.76 ms, 289.30 ms, 191.96 ms (FACT-0107).
- B=224 with a 40 ms window fails. Client p95 13574.29 ms (FACT-0108). 224-client bursts remain open.

## 16. Handoff for next coding session (2026-11-19)

### Goal

High concurrency, low latency, good reliability. Do not move to L4 or Modal until the 224-client burst gate is fixed or formally descoped.

### Current state

- 32-client gate: PASS. Target-driven batching. Three runs: p95 205.76, 289.30, 191.96 ms. FACT-0107.
- 224-client gate: FAIL. With 224 clients, target 224, and a 40 ms window, p50 7854.12 ms and p95 13574.29 ms. FACT-0108.
- B=224 memory is safe. Peak 12.303 GiB, free 1.952 GiB at max_frames=192. FACT-0102.
- All small probes pass: server, backpressure, long text, joins.

### Traps already found

1. Do not compare runs with different probe client limits. Adding `httpx.Limits(max_connections=256)` changed timing. Earlier 100 ms results were not comparable.
2. A 100 ms batch window is flaky at 32 clients. Some runs passed at p95 226 ms; others failed at p95 1994 ms.
3. A fixed 40 ms window is too short for 224 arrivals. Queue p50 is 1630 ms. Do not widen the window above 350 ms as a fix; that eats the TTFA budget.
4. Server `/metrics` `first_chunk_ms` counts all chunks, not only the first chunk of each request. Use client TTFB as the gate.
5. First chunks must have priority. Without it they queue behind continuation chunks.

### Next work

1. Fix the 224-client burst gate. Target p95 first chunk <= 350 ms. Keep RTF below 1.0 and 0 errors.
2. Add per-request TTFA metrics that count only the first chunk of each request.
3. Test with a fixed probe setup. For B32 use default client limits. For B224 use `ARSENAL_LOAD_LIMITS=256`. Record this in the run report.
4. Consider an admission rule that fills a batch by rows, not by a fixed wait alone. Do not add per-row RoPE or shared voice KV without owner permission.
5. Keep the 40 ms failure as a negative fact. Do not delete FACT-0108.

### Key files

- `Code/batch/server.py`: worker batching, priority queue, stream queue bound.
- `Code/batch/batched_stream.py`: per-row voice batching.
- `Code/probes/probe_http_load.py`: HTTP load probe.
- `probes/out/probe_http_load_b32_w300_final.json`: passing 32-client evidence.
- `probes/out/probe_http_load_b224_w40_final.json`: failing 224-client evidence.
- `Skeletons/Probes/probe_http_load_224.md`: READY skeleton for the next session.

### Do not reopen

- True mixed-profile GPU batch with per-row RoPE or shared voice KV. Permission gate required.
- Carried-state chunking. Objective joins pass. Owner listening gate is still pending.
- L4 and Modal. Not in scope for this handoff.

## 17. Owner dislike point (2026-11-19)

- **Dislike point:** `2026-11-19T20:50:20+05:30`.
- This is the start of the HTTP load optimization run `20261119-205020-RUN-02` and commit `e292bed` work.
- Before this point, the verified T4 figure was B=224, p95 112.2 ms, max 118.6 ms, RTF 0.824 (FACT-0064). A 30-burst soak gave p95 119.9 ms (FACT-0087).
- The owner dislikes every change made after this point unless it is revalidated against that earlier B=224 result.
- Changes after this point include one chunk per job, priority queue, larger batch windows, per-row voice batching, and mixed-profile normal-path handling.
- Secondary checkpoint: `2026-11-19T20:11:00+05:30`, commit `fcffdb4`, set the server default `ARSENAL_MAX_BATCH=192` instead of 224. This is also part of the drift.
- The next session must start from the pre-dislike baseline. It must not treat post-point p95 numbers as accepted. Compare first, then revert or keep with evidence.

## 18. Burst recovery after the dislike point (2026-11-20)

**Scope.** Diagnose the 224-client regression. Revalidate against the pre-dislike baseline. Fix code and probe errors. Record what remains.

### 18.1 Baseline (must compare)

| Baseline | Path | Result | Source |
| --- | --- | --- | --- |
| Pre-dislike | Direct `BatchedStream`, conditioned, B=224 | p95 112.2 ms, RTF 0.824 | FACT-0064 |
| Pre-dislike soak | Direct, conditioned, B=224 | p95 119.9 ms, RTF 0.741 | FACT-0087 |
| This session (recheck) | Direct `probe_ttfa_stages.py`, B=224 | p95 97.7 ms, 672/672 < 350 | FACT-0111 |

The model path is not the cause. It is equal or better than the baseline.

### 18.2 What was wrong

| # | Item | Why it was bad | Evidence |
| --- | --- | --- | --- |
| W1 | Metric mismatch | 112 ms is direct in-process. 6–13 s is HTTP with 224 sockets and a queue. The runs are not equal. | FACT-0108, FACT-0112 |
| W2 | Probe client limit | `probe_http_load.py` lost `httpx.Limits` and did not read `ARSENAL_LOAD_LIMITS`. 224 clients shared a small pool. | FACT-0113, diff `284618c` |
| W3 | Profile grouping removed | `_group_key()` returned `None`. Mixed profiles forced the normal path. The conditioned fast path was never used. | `server.py`, FACT-0113 |
| W4 | Batch target cap | `ARSENAL_BATCH_TARGET` default 32. A 224-client burst split into 7 serial batches. | `server.py`, FACT-0113 |
| W5 | Per-row conditioner | `_build_prefixes_with_voices()` called the conditioner once per row. 224 rows = 224 GPU calls. | `batched_stream.py`, FACT-0113 |
| W6 | Event-loop block | `chunks_for()` tokenized in the FastAPI event loop. 224 requests delayed submission and response. | `server.py` |

### 18.3 What was not wrong

| Item | Reason |
| --- | --- |
| Model compute | Direct B=224 first emit is 97.7 ms. No regression. |
| GPU memory at B=224, `max_frames=192` | 12.303 GiB allocated, 1.952 GiB free (FACT-0102). |
| 32-client gate logic | The gate is valid. It passes with the fixed server and probe (FACT-0110). |
| RTF | All HTTP runs stayed below 1.0. |
| One chunk per job / first-chunk priority | These choices keep first chunks ahead of continuations. |

### 18.4 What was fixed

| Fix | Change | File |
| --- | --- | --- |
| F1 | Probe uses async client, start barrier, warm pool, `ARSENAL_LOAD_LIMITS`, and per-request timing. | `Code/probes/probe_http_load.py` |
| F2 | Scheduler drains all waiting jobs first. The time window is a fallback. Default window 150 ms. | `Code/batch/server.py` |
| F3 | One profile id in a batch → conditioned path. Mixed profile ids → one normal-path batch. | `Code/batch/server.py` |
| F4 | Per-row voice prefill uses one batched conditioner call. | `Code/batch/batched_stream.py` |
| F5 | Text chunk results are cached. | `Code/batch/batched_stream.py` |
| F6 | `chunks_for()` runs in a worker thread. | `Code/batch/server.py` |
| F7 | Default `max_batch` is 224. | `Code/batch/server.py` |
| F8 | `/metrics` reports `request_first_chunk_ms` (first chunk per request). | `Code/batch/server.py` |

### 18.5 Evidence

| Check | Command (short) | Result | Key numbers | Run |
| --- | --- | --- | --- | --- |
| Direct B=224 | `probe_ttfa_stages --bs 224 --bursts 3` | PASS | p95 97.7 ms, 672/672 < 350 | `20261120-001821-RUN-02`, FACT-0111 |
| 32 HTTP clients | `probe_http_load` bursts 5 x 32 | PASS | client p95 340.6 ms, server 294.0 ms, 0 err | `20261120-001820-RUN`, FACT-0110 |
| 224 HTTP clients | `probe_http_load` bursts 2 x 224, limits 256, single profile `v1` | FAIL | client p95 7379 ms, server 3166 ms (window 700), 0 err | `20261120-001821-RUN`, FACT-0112 |
| 224 HTTP clients (window 50) | same, `ARSENAL_BATCH_WINDOW_MS=50` | FAIL | client p95 4751 ms, server 1145 ms, queue p95 545 ms | session probe `/tmp/probe224doc.log` |

All runs: RTF < 1.0, no model errors, one T4.

### 18.6 What is not solved

| Item | State | Reason |
| --- | --- | --- |
| 224-client HTTP p95 <= 350 ms | NOT SOLVED | Head-of-line blocking and ingress spread. |
| Server `request_first_chunk_ms` p95 <= 350 ms at 224 | NOT SOLVED | Best observed p95 1145 ms (window 50). Jobs wait for a running batch. |
| Client/server timing gap (~3 s) | NOT SOLVED | Probe and server share 4 vCPU on one host. |
| Continuous batching | NOT IMPLEMENTED | Needs dynamic KV/Mimi state. High risk. |

### 18.7 Real-life issues

1. **Head-of-line blocking.** One batch runs to completion. A late first-chunk job waits 0.5–2 s. Small batches reduce wait but increase total batches.
2. **Ingress spread.** 224 sockets arrive over time. The scheduler can wait (more rows, later start) or start (fewer rows, earlier start).
3. **Host contention.** Load generator and server must run on separate hosts for a fair client gate.
4. **Workload mix.** Mixed profiles, mixed lengths, and long text change the path (conditioned vs normal). Uniform-profile requests are fastest.
5. **Tune per workload.** `ARSENAL_BATCH_WINDOW_MS`, `ARSENAL_BATCH_TARGET`, and `ARSENAL_MAX_BATCH` change the trade-off. Record env in every run.
6. **Out of scope now.** Continuous batching, per-row RoPE, shared voice KV, L4, and Modal. These need owner permission or a new skeleton.

### 18.8 Decision

- Keep **32-client HTTP** as the active gate (PASS).
- Keep **direct B=224** as the model regression gate (PASS).
- Treat **224-client HTTP** as OPEN. Do not claim pass.
- If 224-client HTTP is required, plan continuous batching in a new skeleton before code. Compare each run to the direct baseline.
