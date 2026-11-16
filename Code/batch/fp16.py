"""FP16 backbone helpers for batched streaming (Phase C spike/formalization)."""

from __future__ import annotations

import types
from functools import partial

import torch
import torch.nn.functional as F

import pocket_tts.models.flow_lm as flm


def _fp16_forward(self, sequence, text_embeddings, model_state, sampler_decode_steps, temp, noise_clamp, eos_threshold):
    backbone_dtype = self.input_linear.weight.dtype
    sequence = torch.where(torch.isnan(sequence), self.bos_emb, sequence).to(backbone_dtype)
    text_embeddings = text_embeddings.to(backbone_dtype)
    input_ = self.input_linear(sequence)
    transformer_out = self.backbone(input_, text_embeddings, sequence, model_state=model_state)
    transformer_out = transformer_out.to(torch.float32)
    assert sampler_decode_steps > 0
    transformer_out = transformer_out[:, -1]
    w = self.out_eos.weight.float()
    b = self.out_eos.bias.float() if self.out_eos.bias is not None else None
    out_eos = (transformer_out @ w.t() + (b if b is not None else 0)) > eos_threshold
    noise_shape = transformer_out.shape[:-1] + (self.ldim,)
    std = temp**0.5
    noise = torch.empty(noise_shape, dtype=torch.float32, device=transformer_out.device)
    if noise_clamp is None:
        torch.nn.init.normal_(noise, mean=0.0, std=std)
    else:
        torch.nn.init.trunc_normal_(noise, mean=0.0, std=std, a=-noise_clamp, b=noise_clamp)
    conditioned_flow = partial(self.flow_net, transformer_out)
    if self.flow_type == "lsd":
        decode = flm.lsd_decode
    elif self.flow_type == "flow_matching":
        decode = flm.ot_decode
    elif self.flow_type == "drifting":
        decode = flm.drifting_decode
    elif self.flow_type == "pointwise":
        decode = flm.pointwise_decode
    else:
        raise ValueError(f"Unknown flow type: {self.flow_type}")
    latent = decode(conditioned_flow, noise, sampler_decode_steps)
    return latent.to(backbone_dtype), out_eos


def enable_fp16_backbone(model, mimi_fp16: bool = False):
    """Convert flow_lm backbone to FP16.

    By default the head/sampler and the Mimi decoder stay in FP32. Set
    `mimi_fp16=True` to also convert the Mimi decoder to FP16.
    """
    flm.FlowLMModel.forward = _fp16_forward
    model.flow_lm = model.flow_lm.half()
    model.flow_lm.flow_net = model.flow_lm.flow_net.float()
    model.flow_lm.out_eos = model.flow_lm.out_eos.float()

    def _encode_audio_dtype(self, audio):
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.float16):
            latents = self.mimi.encode_to_latent(audio)
        w = self.flow_lm.speaker_proj_weight
        conditioning = F.linear(latents.to(w.dtype), w).to(self.flow_lm.input_linear.weight.dtype)
        return conditioning

    model._encode_audio = types.MethodType(_encode_audio_dtype, model)

    _orig_decode = model.mimi.decode_from_latent

    if mimi_fp16:
        def decode_half(self, latent, mimi_state):
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                return _orig_decode(latent, mimi_state)

        model.mimi.decode_from_latent = types.MethodType(decode_half, model.mimi)
    else:
        def decode_fp32(self, latent, mimi_state):
            return _orig_decode(latent.float(), mimi_state)

        model.mimi.decode_from_latent = types.MethodType(decode_fp32, model.mimi)
    return model
