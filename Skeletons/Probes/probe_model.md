<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0001
@stageset status: DONE
@stageset priority: P1
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/ideation-pocket-tts-multilingual.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-002-probe-model.md
@stageset implemented_in: .stageset/sessions/coding-ssld-002-probe-model.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Pocket TTS multilingual model facts

## Goal

Answer open questions Q-01 to Q-07 in `Ideas/pocket-tts-multilingual-optimization.md`.
The probe is read-only. It writes one file: `Code/probes/out/probe_model.json`.

## Probe instructions

- Run only `python Code/probes/probe_model.py` from the repository root.
- Do not change model weights, project files, services, or external state.
- Do not expose secrets or credentials.
- Record the exact command and output in a `PROBE` run report.

## Commands

```bash
python Code/probes/probe_model.py
```

## Expected observations

- The command prints one line that starts with `PROBE_MODEL_DONE`.
- The JSON file has the key `sections`.
- `sections` has exactly 7 keys: `env`, `arch`, `voice`, `stream`, `silence`, `batch`, `codec`.
- A failed section holds the key `error` with the traceback text. Other sections still run.
- The script changes the working directory to `Code/model`, so relative paths in `config.yaml` work.
- The script uses `Code/probes/ref/voice.wav` when that file exists. Otherwise it writes a synthetic tone.
- The silence threshold is fixed at `0.01` (float audio, range -1 to 1). The JSON records it.

## Section map

- `env` -> Q-01: Python, torch, CUDA, GPU, package versions, `nvidia-smi` line.
- `arch` -> Q-02: class, parameter total, dtypes, module tree (depth 3), `config.yaml` text.
- `voice` -> Q-04: voice state type, tensor count, size in bytes, deepcopy works or not.
- `stream` -> Q-03: sample rate, method signatures, time to first chunk, chunk sizes.
- `silence` -> Q-05: leading silence in ms, one full generation time, RTF.
- `batch` -> Q-06: names that contain `batch`, parameters of `generate_audio`.
- `codec` -> Q-07: codec-like modules, names that contain `stream`.

## Safety boundary

The probe must not read files outside the repository.
The probe must not write outside `Code/probes/out/`.
The probe must not download, upload, or send network requests.

## Assumptions

ASSUMPTION: A-01 - `pocket_tts` exposes `TTSModel.load_model(config="config.yaml")`. [UNVERIFIED]
ASSUMPTION: A-02 - `TTSModel` has `get_state_for_audio_prompt(path)` and `generate_audio(state, text)`. [UNVERIFIED]
ASSUMPTION: A-03 - `TTSModel` has `generate_audio_stream(state, text)`. [UNVERIFIED]
ASSUMPTION: A-04 - `TTSModel` is a torch module and has a `sample_rate` attribute. [UNVERIFIED]
ASSUMPTION: A-05 - The community finetune keeps the public API of the base Kyutai model. [UNVERIFIED]

## Checks

### CHECK-PROBE-MODEL-01

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_model.json')); print(len(d['sections']))"`
- Predicted output: `7`
- Pass condition: the command prints `7`.
- Fail condition: the file is missing or the command prints another number.

### CHECK-PROBE-MODEL-02

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_model.json')); print(sum(1 for s in d['sections'].values() if 'error' in s))"`
- Predicted output: `0`
- Pass condition: the command prints `0`.
- Fail condition: the command prints a number above 0. Send the error text to the planner.

## References

- `Ideas/pocket-tts-multilingual-optimization.md`
- `LivingDocs/SSLD-002-probe-model.md`
