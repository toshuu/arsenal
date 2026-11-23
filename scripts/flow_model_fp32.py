"""Shared builder for the patched flow step and its static example inputs."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import torch

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
BATCH = 8
FRAMES = 64


class FlowStep(torch.nn.Module):
    def __init__(self, model, names):
        super().__init__()
        self.m = model
        self.names = names

    def forward(self, text_tokens, latent, audio_cond, *flat):
        st = {}
        i = 0
        for n in self.names:
            st[n] = {"offset": flat[i], "pad": flat[i + 1], "cache": flat[i + 2]}
            i += 3
        out, eos = self.m._run_flow_lm_and_increment_step(st, text_tokens, latent, audio_cond)
        outs = [out, eos]
        for n in self.names:
            outs.extend([st[n]["offset"], st[n]["pad"], st[n]["cache"]])
        return tuple(outs)


def build() -> tuple[torch.nn.Module, tuple]:
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, str(ROOT / "vendor" / "pocket-tts"))
    sys.path.insert(0, str(ROOT / "Code"))
    sys.path.insert(0, str(ROOT / "Code" / "probes"))
    os.chdir(ROOT / "Code" / "model")
    from pocket_tts import TTSModel
    from batch.batched_stream import BatchedStream, set_state_padding
    from pocket_tts.modules.stateful_module import init_states
    from bench_batch_server import make_texts

    model = TTSModel.load_model(config="config.yaml").to("cuda").eval().float()
    model.temp = 0.0
    sp = BatchedStream(
        model, voice="/kaggle/working/refHD.wav", voice_seconds=4.0, max_first_tokens=16
    )
    sp.voice = sp.voice.float()
    if sp.voice_state is not None:
        sp.voice_state = {k: {sk: sv.float() if sv.is_floating_point() else sv for sk, sv in v.items()} for k, v in sp.voice_state.items()}
    prefix, pad, _ = sp._build_prefixes(make_texts(BATCH)[:BATCH])
    state = init_states(model.flow_lm, BATCH, 512)
    set_state_padding(state, pad)
    names = list(state.keys())
    wrap = FlowStep(model, names).eval()
    flat = []
    for n in names:
        for key in ("offset", "pad", "cache"):
            flat.append(state[n][key])
    args = tuple(t.float() if t.is_floating_point() else t for t in (
        torch.empty(BATCH, 0, dtype=torch.int64, device="cuda"),
        model.flow_lm.bos_emb.view(1, 1, -1).expand(BATCH, 1, -1),
        prefix,
    ) + tuple(flat))
    return wrap, args
