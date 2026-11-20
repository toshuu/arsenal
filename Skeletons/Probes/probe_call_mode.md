<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0007
@stageset status: READY
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 0
@stageset planned_in: .stageset/sessions/plan-call-mode.md
@stageset last_updated_in: .stageset/sessions/plan-call-mode.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: call-mode ramp, seams, mixed load, cancel

## Goal

Measure the implemented call mode on one T4 in-container:

1. Max B at first-chunk p95 <= 350, 200, and 100 ms.
2. Zero underruns and gap-free continuation at the target B.
3. Mixed call and normal load.
4. Cancel cleanup.
5. Normal HTTP regression.

## Probe instructions

- Run in-container on the Modal T4. Use no public proxy.
- Use one conditioned voice profile for all call streams. Use the same profile for
  normal requests in the mixed test.
- Ramp B = 224, 320, 448, 512, 640, 768, 896, 1024. Stop at the first failure.
- Arrivals: one burst per B, and Poisson at 200, 400, and 800 starts per second.
- Sweep `window` = 0, 5, 10, 25 ms.
- Sweep first `max_frames` = 24, 32, 48.
- Use 3 repeats per cell. Report p95 of the repeats.
- Set `ARSENAL_MAX_QUEUE`, `ARSENAL_MAX_ROWS`, `ARSENAL_MAX_BATCH`, and
  `ARSENAL_BATCH_TARGET` to at least the top B.
- Use `ARSENAL_DEBUG=1` and read `/metrics`, `/debug/vram`.
- Write only to `probes/out/` and StageSet files.
- Stop the app after: `modal app stop arsenal-tts-t4 -y`.

## Commands

```text
modal deploy Code/deploy/modal_app.py
curl "$URL/health"
# ramp
curl "$URL/debug/callramp?b=<B>&arrival=burst|poisson&rate=<R>&window=<W>&first_max_frames=<MF>&repeats=3&profile=v1"
# mixed: 128 call streams plus 32 normal HTTP
curl "$URL/debug/callmixed?call=128&normal=32&window=<W>&first_max_frames=<MF>"
# cancel: 50 percent mid-stream
curl "$URL/debug/callcancel?b=<B>&cancel_frac=0.5&seconds=10"
# normal regression
ARSENAL_LOAD_BURSTS=5 ARSENAL_LOAD_PER_BURST=32 ARSENAL_POCKET_TTS=/kaggle/working/pocket-tts python Code/probes/probe_http_load.py
modal app stop arsenal-tts-t4 -y
```

## Seam definition

For each stream, `t0` is the first byte of chunk 1. `dur(n)` is the audio duration
of chunk `n` in seconds. The playback end of chunk `n` is `t0 + sum(dur(1..n))`.

```text
slack(n) = t_first_byte(n+1) - playback_end(n)     # seconds
underrun = slack(n) < 0
```

Report per stream: underrun count, slack p5, slack p50, slack p95. Target:
underrun count 0 and slack p5 >= 0.

## Expected observations

- A table: `class | B | arrival | window | first_max_frames | peak VRAM MB | first p95 | underruns | slack p5 | errors`.
- Max B per gate.
- Mixed table: call first-chunk p95, call continuation slack, normal p95.
- Cancel: `active_call_sessions` 0, queue depth 0, VRAM change under 100 MB.
- Five joined WAV files for listening.
- Fact rows for max B and seam results.

## Safety boundary

- Do not change model weights.
- Do not send data outside the machine.
- Do not edit project code in this probe.
- Do not claim a pass without saved JSON and WAV files.
- Stop the GPU after the probe.

## Assumptions

ASSUMPTION: A-47 - The client clocks the first byte correctly for a WebSocket
binary frame. [UNVERIFIED]
ASSUMPTION: A-48 - `max_frames=32` holds about 2 s of audio for a 4 to 8 word first
chunk at 12.5 Hz. [UNVERIFIED]
ASSUMPTION: A-49 - Continuation chunks can generate faster than realtime at high B
with the `call_cont` class. [UNVERIFIED]

## Checks

### CHECK-CALL-RAMP-01 - max B per gate

- Command: the ramp above.
- Predicted output: a JSON per cell with `client.p95_ms`, `server.first_chunk_p95_ms`, `peak_vram_mb`, `errors`.
- Pass condition: a saved JSON shows max B with p95 <= 350 ms and 0 errors.
- Fail condition: B=224 fails 350 ms, or any OOM or error.

### CHECK-CALL-RAMP-02 - 200 ms and 100 ms gates

- Command: the ramp above at the best window and `max_frames`.
- Predicted output: a JSON per gate.
- Pass condition: report max B for 200 ms and 100 ms. A gate with no pass B is
  reported as `none`, not as a pass.
- Fail condition: a claimed pass without saved JSON.

### CHECK-CALL-SEAM-01 - no underruns

- Command: 60 s streams at the max B that passed 350 ms, best window and `max_frames`.
- Predicted output: `{"underruns": 0, "slack_p5_ms": >= 0}`
- Pass condition: 0 underruns and slack p5 >= 0 ms on every stream.
- Fail condition: any underrun or negative slack p5.

### CHECK-CALL-MIXED-01 - call first chunk beats normal load

- Command: 128 call streams plus 32 normal HTTP requests at once.
- Predicted output: call first-chunk p95 <= 350 ms, normal p95 recorded.
- Pass condition: call p95 <= 350 ms and 0 errors in both classes.
- Fail condition: call p95 above 350 ms. Then write a READY preemption plan only.

### CHECK-CALL-CANCEL-01 - cancel cleanup

- Command: the cancel test above.
- Predicted output: `{"active_call_sessions": 0, "queue_depth": 0, "vram_delta_mb": < 100}`
- Pass condition: all three values hold after 10 s.
- Fail condition: a stuck session, a non-zero queue, or VRAM growth.

### CHECK-CALL-LISTEN-01 - seam listening sample

- Command: write 5 joined call WAVs to `probes/out/call_mode/`.
- Predicted output: 5 files, each with at least 3 chunks.
- Pass condition: the owner reports no click and no gap at the joins.
- Fail condition: the owner reports a defect. Then set `spec_revision` +1 and fix
  the boundary rule.

## References

- `Ideas/IDEA-0007-dual-service-call-mode.md`
- `Skeletons/Code/batch/job_classes.py`
- `Skeletons/Code/batch/call_chunker.py`
- `Skeletons/Code/batch/server.py`
- `Skeletons/Probes/probe_call_ceiling.md`
- `.stageset/runs/20261120-142010-RUN.md`
