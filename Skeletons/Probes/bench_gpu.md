<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0001
@stageset status: DONE
@stageset priority: P1
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/event-plan-gpu-baseline.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-004-gpu-baseline.md
@stageset implemented_in: .stageset/sessions/coding-ssld-004-gpu-baseline.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: T4 single-stream baseline

## Goal

Measure one GPU stream on the Tesla T4. The probe answers the Phase 1 need for
first-audio latency, real-time factor, memory, and leading silence.

## Probe instructions

- Run `python Code/probes/bench_gpu.py --runs 20 --warmup 3` from the repository root.
- The script writes only `Code/probes/out/bench_gpu.json`.
- Do not change model weights, project files, services, or external state.
- Do not expose secrets or credentials.

## Commands

```bash
python Code/probes/bench_gpu.py --runs 20 --warmup 3
```

## Expected observations

- The command prints one line that starts with `BENCH_GPU_DONE`.
- The JSON file has `runs` equal to 20 and `errors` with length 0.
- The JSON file has these keys: `summary`, `full_generate`, `peak_allocated_mb`.
- `summary` holds `p50_first_chunk_ms`, `p95_first_chunk_ms`, `p50_rtf`, and `p95_rtf`.
- `full_generate` holds `leading_silence_ms` and `rtf`.
- The script uses `Code/probes/ref/voice.wav` when that file exists. Otherwise it writes a synthetic tone.
- The script calls `model.to("cuda:0").eval()` before it measures.
- The script calls `torch.cuda.reset_peak_memory_stats()` before the measured runs.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-06 - `TTSModel.to("cuda")` moves the full model to the GPU. [UNVERIFIED]
ASSUMPTION: A-07 - `generate_audio_stream` runs on the GPU model. [UNVERIFIED]
ASSUMPTION: A-08 - `torch.cuda.max_memory_allocated` reports the GPU memory peak. [UNVERIFIED]

## Checks

### CHECK-BENCH-GPU-01

- Command: `python -c "import json; d=json.load(open('Code/probes/out/bench_gpu.json')); print(d['runs'], len(d['errors']))"`
- Predicted output: `20 0`
- Pass condition: the command prints `20 0`.
- Fail condition: the file is missing or the command prints another value.

### CHECK-BENCH-GPU-02

- Command: `python -c "import json; d=json.load(open('Code/probes/out/bench_gpu.json')); print(d['summary']['p50_first_chunk_ms'] > 0 and d['summary']['p50_rtf'] > 0)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: a summary value is missing or not above 0.

## References

- `Ideas/pocket-tts-multilingual-optimization.md`
- `LivingDocs/SSLD-004-gpu-baseline.md`
- `Code/pocket-tts-bench/schema.json`
