<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/server.py
@stageset source_idea: IDEA-0005
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset last_updated_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset implemented_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: HTTP serving layer

## Purpose

Serve one bounded batch worker over HTTP. Reject overload. Cancel queued work.
Report health and metrics.

## Contract

- `POST /tts` takes `{text, max_frames?}` and returns `audio/wav`.
- `POST /tts/batch` takes `{texts, max_frames?}` and returns a JSON list of base64 WAV items.
- `GET /health` returns readiness, queue depth, and counters.
- The queue is bounded by `ARSENAL_MAX_QUEUE`.
- The worker takes at most `ARSENAL_MAX_BATCH` jobs per call.
- A full queue returns 503. An empty text returns 422. A long text returns 413.
- A request above `ARSENAL_TIMEOUT_S` returns 504.
- A client disconnect sets the job stop event and drops queued work.

## Edge cases

- Engine not ready: `/health` returns 503.
- One failed batch: every job in that batch gets the error. The worker stays alive.
- More than one job in a batch: texts are flattened, synthesized once, then split back by job.
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
- Pass condition: the probe run `20261119-191120-RUN` shows both results.
- Fail condition: readiness is false or the WAV response is empty.

## References

- `Ideas/IDEA-0005-long-text-and-production-readiness.md`
- `Code/batch/batched_stream.py`
- `Code/probes/check_server.py`
- `.stageset/runs/20261119-191119-RUN-04.md`
