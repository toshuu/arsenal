import os, sys, time, torch, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')

import pocket_tts.models.flow_lm as flm
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream

# Monkeypatch: run backbone in fp16, keep head/sampler in fp32
_orig_forward = flm.FlowLMModel.forward
def fp16_forward(self, sequence, text_embeddings, model_state, sampler_decode_steps, temp, noise_clamp, eos_threshold):
    sequence = torch.where(torch.isnan(sequence), self.bos_emb, sequence)
    input_ = self.input_linear(sequence)
    transformer_out = self.backbone(input_, text_embeddings, sequence, model_state=model_state)
    transformer_out = transformer_out.to(torch.float32)
    assert sampler_decode_steps > 0
    transformer_out = transformer_out[:, -1]
    # out_eos in fp32
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
    from functools import partial
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
    return latent, out_eos

flm.FlowLMModel.forward = fp16_forward

m = TTSModel.load_model(config='config.yaml').to('cuda').eval()
m.flow_lm = m.flow_lm.half()
# keep mimi and other in fp32
m.temp = 0.0
bs = BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
texts = ["Hello, this is a short test sentence.",
         "Good morning. The weather is nice today.",
         "Testing one two three four five six seven eight nine ten."]
try:
    # warmup
    bs.stream(texts[:1], max_frames=4)
    out = bs.stream(texts, max_frames=8)
    ok = all(x.numel()>0 and torch.isfinite(x).all() for x in out)
    print('SPIKE_OK', ok, 'shapes', [x.shape[0] for x in out])
except Exception as e:
    import traceback
    traceback.print_exc()
