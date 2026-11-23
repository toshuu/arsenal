---
type: CODING
time: 2026-11-23T17:03:29+05:30
summary: Sideline TRT attempt: static cache patch is bit-exact, but exported graph fails numeric parity.
paths: patches/attention.patch; scripts/; .stageset/runs/20261123-170329-RUN.md
related: FACT-0171; 20261123-170329-RUN
commit: -
remote: -
branch: sideline/trt
---

# Session notes

## Work

- Created isolated worktree `/kaggle/working/arsenal-trt-sideline` on branch
  `sideline/trt`. Main worktree was not changed.
- Installed TRT stack in the Python environment with `--no-deps`.
- Patched attention cache writes to remove tensor-to-Python conversion and
  data-dependent branches. Added explicit batch indices and an additive float
  attention mask.
- Verified cache parity and bit-exact audio on 5 texts.
- Tried torch_tensorrt dynamo, TorchScript IR, and ONNX + TRT engine.

## Result

- Engine builds, but numeric parity fails. ORT also fails. No TRT gain.
- Stopped after three failure modes were removed. The remaining fault needs a
  deeper per-submodule export investigation.

## Follow-up

- Find the first attention op that diverges in ORT.
- Do not merge sideline into main until parity and gain are proved.
