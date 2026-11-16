"""Pre-cast FP16 decode weights: save once at image time, load to GPU at boot."""

from __future__ import annotations

from pathlib import Path

import torch


_DECODER_PREFIXES = ("decoder.", "decoder_transformer.", "upsample.")


def _targets(model):
    for name, param in model.mimi.named_parameters():
        if name.startswith(_DECODER_PREFIXES):
            yield f"mimi.{name}", param
    for name, param in model.flow_lm.named_parameters():
        if name.startswith(("input_linear", "backbone")):
            yield f"flow_lm.{name}", param


def save_fp16_weights(model, path: str | Path) -> None:
    state = {
        name: param.detach().half().cpu()
        for name, param in _targets(model)
        if param.is_floating_point()
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, str(path))


def load_fp16_weights(model, path: str | Path) -> None:
    state = torch.load(str(path), map_location="cuda")
    for name, param in _targets(model):
        if name not in state:
            continue
        if param.dtype != state[name].dtype:
            param.data = param.data.to(dtype=state[name].dtype)
        param.data.copy_(state[name])
