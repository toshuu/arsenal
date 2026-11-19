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
