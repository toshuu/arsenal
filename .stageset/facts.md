# Verified environment facts

This file contains facts that a run report has confirmed. Do not put guesses or untested claims here.

Use one row per fact. Link the run report that proves the fact. Add a new row when a fact changes. Mark the old row as superseded. Do not delete the history.

| Fact ID | Date | Verified fact | Scope | State | Source run |
| --- | --- | --- | --- | --- | --- |
| FACT-0001 | 2026-11-15 | The PyPI package `pocket-tts` 4.0.1 installs the module `pocket_tts` and exposes `TTSModel.load_model`, `generate_audio`, `generate_audio_stream`, and `get_state_for_audio_prompt`. | Environment | CURRENT | `.stageset/runs/20261115-130213-RUN.md` |
| FACT-0002 | 2026-11-15 | The model repo `Thanushttk/pocket-tts-multilingual` holds `config.yaml`, `model.safetensors`, and `tokenizer.model` in 419 MB. The config has 6 flow layers, `d_model` 1024, 16 heads, 24 kHz, and frame rate 12.5 Hz. | Project | CURRENT | `.stageset/runs/20261115-130213-RUN-02.md` |
