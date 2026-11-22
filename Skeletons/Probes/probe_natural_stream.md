<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/plan-natural-streaming.md
@stageset last_updated_in: .stageset/sessions/plan-natural-streaming.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: natural stream text policies

## Goal

Measure three call text policies on one T4:

1. `legacy`: `max_first_tokens=16`, current 192 frame limit.
2. `sentence`: no first-token cut, sentence chunks, 224 frame limit.
3. `utterance`: no first-token cut, whole text, 512 frame limit.

Measure first-frame p50/p95, batch wall, per-row last-frame time, long-gap
count, peak VRAM, and saved WAVs. Use one mixed batch of short and long calls.

## Probe instructions

- Run `python Code/probes/probe_natural_stream.py` on a T4.
- Use `/kaggle/working/refHD.wav` as the reference voice.
- Use `max_frames` from the mode table in the probe.
- Run with `compact=True` and `decode_group=1`.
- Do not change project behavior. The probe uses `BatchedStream` directly.
- Write only to `Code/probes/out/natural_stream/` and StageSet files.
- Stop after the probe. Do not leave a GPU job active.

## Commands

```text
python Code/probes/probe_natural_stream.py --mode legacy --batch 2 --reps 1 --mix same --out Code/probes/out/natural_stream/smoke_legacy.json
python Code/probes/probe_natural_stream.py --mode sentence --batch 2 --reps 1 --mix same --out Code/probes/out/natural_stream/smoke_sentence.json
python Code/probes/probe_natural_stream.py --mode utterance --batch 2 --reps 1 --mix same --out Code/probes/out/natural_stream/smoke_utterance.json
python Code/probes/probe_natural_stream.py --mode legacy --batch 64 --reps 2 --mix same --out Code/probes/out/natural_stream/b64_legacy.json
python Code/probes/probe_natural_stream.py --mode sentence --batch 64 --reps 2 --mix same --out Code/probes/out/natural_stream/b64_sentence.json
python Code/probes/probe_natural_stream.py --mode utterance --batch 64 --reps 2 --mix same --out Code/probes/out/natural_stream/b64_utterance.json
python Code/probes/probe_natural_stream.py --mode sentence --batch 64 --reps 2 --mix mixed --out Code/probes/out/natural_stream/b64_mixed_sentence.json
python Code/probes/probe_natural_stream.py --mode utterance --batch 64 --reps 2 --mix mixed --out Code/probes/out/natural_stream/b64_mixed_utterance.json
```

## Expected observations

- One JSON per run with `mode`, `batch`, `mix`, `reps`, `first_frame_ms`,
  `batch_wall_ms`, `last_frame_ms`, `gaps`, `vram_peak_mb`, and `runs`.
- WAV files for the first 5 rows: `Code/probes/out/natural_stream/<mode>_<batch>_<mix>_<row>.wav`.
- `first_frame_ms.p95` for `legacy` should be lower than `utterance`.
- `batch_wall_ms` for `utterance` should be larger than `sentence` and `legacy`.
- `last_frame_ms.max` shows the tail. It is not a new-call wait.

## Safety boundary

- Do not change model weights.
- Do not send data outside the machine.
- Do not edit project code in this probe.
- Do not claim a pass without saved JSON and WAV files.

## Assumptions

ASSUMPTION: A-50 - `max_allowed_frames=512` lets the 114-token story stay in one chunk at `max_tokens=512`. [UNVERIFIED]
ASSUMPTION: A-51 - `BatchedStream` returns one audio tensor per row with internal chunks joined. [VERIFIED]
ASSUMPTION: A-52 - `compact=True` removes finished rows and does not raise. [VERIFIED]

## Checks

### CHECK-NATURAL-SMOKE-01 - three modes run

- Command: the three smoke commands above.
- Predicted output: 3 JSON files with `first_frame_ms.p95` numbers and no error.
- Pass condition: all 3 exits are 0.
- Fail condition: any import error, OOM, or missing JSON.

### CHECK-NATURAL-B64-01 - B=64 same text

- Command: the three B=64 same commands above.
- Predicted output: 3 JSON files with `batch_wall_ms` and `first_frame_ms.p95`.
- Pass condition: no error and `first_frame_ms.count` is 64.
- Fail condition: any error, OOM, or missing row.

### CHECK-NATURAL-MIX-01 - B=64 mixed text

- Command: the two mixed commands above.
- Predicted output: 2 JSON files. Short rows must have an earlier `last_frame_ms`
  than long rows.
- Pass condition: `last_frame_ms.max` is greater than `last_frame_ms.min` for
  each mixed run.
- Fail condition: all rows end at the same time, or any error.

### CHECK-NATURAL-LISTEN-01 - WAV files exist

- Command: `ls Code/probes/out/natural_stream/*.wav`.
- Predicted output: at least 10 WAV files.
- Pass condition: files exist and are not empty.
- Fail condition: no WAV files.

## References

- `Ideas/IDEA-0008-natural-live-call-streaming.md`
- `Code/batch/batched_stream.py`
- `Code/batch/call_chunker.py`
- `Code/batch/pause_compress.py`
