<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/server.py
@stageset source_idea: IDEA-0005
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 2
@stageset implemented_revision: 2
@stageset planned_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset last_updated_in: .stageset/sessions/coding-voice-profile-selection.md
@stageset implemented_in: .stageset/sessions/coding-voice-profile-selection.md
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
- Without `voice_profile`, the server uses the reference voice clip on the normal path.
- With `voice_profile`, the server loads that id from `ARSENAL_VOICE_PROFILES` and uses its conditioned state.
- `GET /health` returns readiness, queue depth, and counters.
- The queue is bounded by `ARSENAL_MAX_QUEUE`.
- The worker takes at most `ARSENAL_MAX_BATCH` jobs per call.
- A full queue returns 503. An empty text returns 422. A long text returns 413.
- A request above `ARSENAL_TIMEOUT_S` returns 504.
- A client disconnect sets the job stop event and drops queued work.
- An unknown `voice_profile` returns 400.
- A profile batch with mixed first-chunk token lengths returns 422.
- The worker groups jobs by profile id and first-chunk token length before synthesis.

## Edge cases

- Engine not ready: `/health` returns 503.
- One failed batch: every job in that batch gets the error. The worker stays alive.
- More than one job in a batch: jobs with the same profile id and first-chunk token length are flattened, synthesized once, then split back by job.
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

### CHECK-SERVER-03 - profile image wiring

- Command: `python Code/batch/build_voice_profiles.py OUT_DIR id=voice.wav`
- Predicted output: `PROFILE id OUT_DIR/id.pt`.
- Pass condition: the run report shows the file exists and a server started with `ARSENAL_VOICE_PROFILES=id=OUT_DIR/id.pt` serves a profile request with 200.
- Fail condition: the build fails or the server cannot load the id.

## References

- `Ideas/IDEA-0005-long-text-and-production-readiness.md`
- `Code/batch/batched_stream.py`
- `Code/probes/check_server.py`
- `Code/batch/build_voice_profiles.py`
- `Code/batch/VOICE_PROFILES.md`
- `.stageset/runs/20261119-191119-RUN-04.md`
