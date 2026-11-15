import os, sys, torch, logging, types
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')
import torch.nn.functional as F
import pocket_tts.models.flow_lm as flm
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream

def make_m(fp16=False):
    m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); m.temp=0.0
    if not fp16: return m
    def fp16_forward(self, sequence, text_embeddings, model_state, sampler_decode_steps, temp, noise_clamp, eos_threshold):
        backbone_dtype = self.input_linear.weight.dtype
        sequence = torch.where(torch.isnan(sequence), self.bos_emb, sequence).to(backbone_dtype)
        text_embeddings = text_embeddings.to(backbone_dtype)
        input_ = self.input_linear(sequence)
        transformer_out = self.backbone(input_, text_embeddings, sequence, model_state=model_state)
        transformer_out = transformer_out.to(torch.float32)[:, -1]
        w = self.out_eos.weight.float(); b = self.out_eos.bias.float() if self.out_eos.bias is not None else None
        out_eos = (transformer_out @ w.t() + (b if b is not None else 0)) > eos_threshold
        noise_shape = transformer_out.shape[:-1] + (self.ldim,)
        std = temp**0.5
        noise = torch.zeros(noise_shape, dtype=torch.float32, device=transformer_out.device) if std==0 else torch.randn(noise_shape, dtype=torch.float32, device=transformer_out.device)*std
        from functools import partial
        conditioned_flow = partial(self.flow_net, transformer_out)
        decode = {'lsd':flm.lsd_decode,'flow_matching':flm.ot_decode,'drifting':flm.drifting_decode,'pointwise':flm.pointwise_decode}[self.flow_type]
        latent = decode(conditioned_flow, noise, sampler_decode_steps)
        return latent.to(backbone_dtype), out_eos
    flm.FlowLMModel.forward = fp16_forward
    m.flow_lm = m.flow_lm.half()
    m.flow_lm.flow_net = m.flow_lm.flow_net.float()
    m.flow_lm.out_eos = m.flow_lm.out_eos.float()
    def _encode_audio_dtype(self, audio):
        with torch.no_grad(): latents = self.mimi.encode_to_latent(audio)
        w = self.flow_lm.speaker_proj_weight
        return F.linear(latents.to(w.dtype), w).to(self.flow_lm.input_linear.weight.dtype)
    m._encode_audio = types.MethodType(_encode_audio_dtype, m)
    _orig_decode = m.mimi.decode_from_latent
    def decode_fp32(self, latent, mimi_state): return _orig_decode(latent.float(), mimi_state)
    m.mimi.decode_from_latent = types.MethodType(decode_fp32, m.mimi)
    return m

texts=["Hello, this is a short test sentence.","Good morning. The weather is nice today.","Testing one two three four five six seven eight nine ten."]
m=make_m(False); bs=BatchedStream(m,'/kaggle/working/arsenal/Code/probes/ref/voice.wav')
a32=bs.stream([texts[0]],max_frames=32)[0].cpu()
del m,bs; torch.cuda.empty_cache()
m=make_m(True); bs=BatchedStream(m,'/kaggle/working/arsenal/Code/probes/ref/voice.wav')
a16=bs.stream([texts[0]],max_frames=32)[0].cpu()
print('maxdiff', float((a32-a16).abs().max()), 'corr', float(torch.corrcoef(torch.stack([a32,a16]))[0,1]) if a32.std()>0 and a16.std()>0 else None)
