---
type: CODING
time: "2026-11-15T13:03:58+05:30"
summary: Complete SSLD-002 probe and record the model facts.
paths: Code/probes/probe_model.py; Code/probes/ref/voice.wav; Code/probes/out/probe_model.json; Skeletons/Probes/probe_model.md; LivingDocs/SSLD-002-probe-model.md; .stageset/runs/20261115-130345-RUN.md; .stageset/runs/20261115-130345-RUN-02.md
related: IDEA-0001; SSLD-002; 20261115-130345-RUN; 20261115-130345-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Use `Code/model/samples/english.wav` as the reference voice. Convert it to PCM16 for portability.
- Keep the probe output in `Code/probes/out/` and ignore it in Git.

## Outcomes

- The probe ran on the real model with 7 sections and 0 errors.
- The model has 109.5M FP32 parameters, 24 kHz audio, and 12.5 Hz frames.
- The voice state is 3.844 MB FP32 and deepcopies in 5.1 ms.
- On CPU, the first stream chunk arrives after 361.6 ms. RTF is 0.6476.
- Leading silence is 5.5 ms.
- The model has no native batch argument.
- The codec has streaming modules.
- All 4 tasks of SSLD-002 are DONE.

## Follow-up

- Run SSLD-003 to create the benchmark harness workspace.
- Test the model on the T4 GPU. The probe used CPU.
- Test whether `model.eval()` changes the audio or the speed.
