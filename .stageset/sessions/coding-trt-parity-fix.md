---
type: CODING
time: 2026-11-23T17:35:12+05:30
summary: Fix TRT parity by enlarging the KV cache and exporting a pure fp32 graph; verify speed gain.
paths: patches/attention.patch; scripts/export_onnx_fp32.py; scripts/build_engine.py; out/export
related: FACT-0171; FACT-0172; 20261123-170329-RUN; 20261123-173512-RUN
commit: -
remote: -
branch: sideline/trt
---

# Session notes

## Work

- Found two causes of the wrong TRT output. The KV cache was too small, and
  the fp16 graph mixed LayerNorm constant types.
- Enlarged the exported cache to 512 frames.
- Exported a pure fp32 graph, then built FP32 and FP16 TRT engines.
- Verified parity against eager and measured flow-step latency.

## Result

- TRT FP16 parity: maxdiff 0.0133, corr 0.999998, eos match.
- Flow-step p50: 53.10 ms TRT vs 57.22 ms fp16 eager. Gain 1.08x.
- Audio with the sideline patch is bit-exact on 5 texts.

## Follow-up

- Integrate the engine into the server and measure WS gates before any merge.
- Mimi export is still open.
