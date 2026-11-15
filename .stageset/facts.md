# Verified environment facts

This file contains facts that a run report has confirmed. Do not put guesses or untested claims here.

Use one row per fact. Link the run report that proves the fact. Add a new row when a fact changes. Mark the old row as superseded. Do not delete the history.

| Fact ID | Date | Verified fact | Scope | State | Source run |
| --- | --- | --- | --- | --- | --- |
| FACT-0001 | 2026-11-15 | The PyPI package `pocket-tts` 4.0.1 installs the module `pocket_tts` and exposes `TTSModel.load_model`, `generate_audio`, `generate_audio_stream`, and `get_state_for_audio_prompt`. | Environment | CURRENT | `.stageset/runs/20261115-130213-RUN.md` |
| FACT-0002 | 2026-11-15 | The model repo `Thanushttk/pocket-tts-multilingual` holds `config.yaml`, `model.safetensors`, and `tokenizer.model` in 419 MB. The config has 6 flow layers, `d_model` 1024, 16 heads, 24 kHz, and frame rate 12.5 Hz. | Project | CURRENT | `.stageset/runs/20261115-130213-RUN-02.md` |
| FACT-0003 | 2026-11-15 | The loaded model has 109,501,826 parameters, all FP32. `sample_rate` is 24000. The codec frame rate is 12.5 Hz, so one frame is 80 ms and 1920 samples. | Project | CURRENT | `.stageset/runs/20261115-130345-RUN-02.md` |
| FACT-0004 | 2026-11-15 | The voice state is a `dict` with 18 tensors and 3.844 MB in FP32. `copy.deepcopy` of the voice state takes 0.0051 s. | Project | CURRENT | `.stageset/runs/20261115-130345-RUN-02.md` |
| FACT-0005 | 2026-11-15 | On CPU, `generate_audio_stream` gives the first 1920-sample chunk after 361.6 ms. A full 2.48 s generation takes 1.606 s (RTF 0.6476). Leading silence is 5.5 ms. | Project | CURRENT | `.stageset/runs/20261115-130345-RUN-02.md` |
| FACT-0006 | 2026-11-15 | `generate_audio` has no batch argument and the model has no name that contains `batch`. The codec uses streaming modules. The loaded model reports `training: True`. | Project | CURRENT | `.stageset/runs/20261115-130345-RUN-02.md` |
