<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: requirements.txt
@stageset source_idea: IDEA-0001
@stageset status: READY
@stageset priority: P1
@stageset spec_revision: 1
@stageset implemented_revision: 0
@stageset planned_in: .stageset/sessions/ideation-pocket-tts-multilingual.md
@stageset last_updated_in: .stageset/sessions/event-arsenal-batch-1-ready.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Skeleton: Code/requirements.txt (setup)

## Purpose

- List the Python packages for Arsenal.
- Install them. Download the model files into `Code/model`.

## Contract

- `Code/requirements.txt` has 3 lines: `pocket-tts`, `huggingface_hub`, `numpy`.
- Do not pin versions. The probe records the installed versions as facts.
- Model repo: `Thanushttk/pocket-tts-multilingual`. Download target: `Code/model`.
- `Code/model` must hold `config.yaml`, `model.safetensors`, and `tokenizer.model`.
- Do not commit `Code/model` or `Code/probes/out`. Add them to `.gitignore`.

ASSUMPTION: A-01 - The PyPI package `pocket-tts` installs the module `pocket_tts`. [UNVERIFIED]
ASSUMPTION: A-02 - The model repo holds the three files named in the Contract. [UNVERIFIED]

## Checks

### CHECK-SETUP-01

- Command: `python -c "import pocket_tts; print('pocket_tts ok')"`
- Predicted output: `pocket_tts ok`
- Pass condition: the command prints `pocket_tts ok`.
- Fail condition: the command raises ImportError.

### CHECK-SETUP-02

- Command: `python -c "import os; print(sorted(f for f in ['config.yaml','model.safetensors','tokenizer.model'] if os.path.exists('Code/model/'+f)))"`
- Predicted output: `['config.yaml', 'model.safetensors', 'tokenizer.model']`
- Pass condition: the command prints the 3 file names.
- Fail condition: the command prints fewer than 3 names.
