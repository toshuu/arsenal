import os, sys, time, torch, logging, types
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
sys.path.insert(0, '/kaggle/working/arsenal/Code/probes')
os.chdir('/kaggle/working/arsenal/Code/model')
import torch.nn.functional as F
import pocket_tts.models.flow_lm as flm
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from bench_batch_server import make_texts

def patch_fp16(model):
    def fp16_forward(self, sequence, text_embeddings, model_state, sampler_decode_steps, temp, noise_clamp, eos_threshold):
        backbone_dtype = self.input_linear.weight.dtype
        sequence = torch.where(torch.isnan(sequence), self.bos_emb, sequence).to(backbone_dtype)
        text_embeddings = text_embeddings.to(backbone_dtype)
        input_ = self.input_linear(sequence)
        transformer_out = self.backbone(input_, text_embeddings, sequence, model_state=model_state)
        transformer_out = transformer_out.to(torch.float32)
        transformer_out = transformer_out[:, -1]
        w = self.out_eos.weight.float()
        b = self.out_eos.bias.float() if self.out_eos.bias is not None else None
        out_eos = (transformer_out @ w.t() + (b if b is not None else 0)) > eos_threshold
        noise_shape = transformer_out.shape[:-1] + (self.ldim,)
        std = temp**0.5
        noise = torch.empty(noise_shape, dtype=torch.float32, device=transformer_out.device)
        if noise_clamp is None: torch.nn.init.normal_(noise, mean=0.0, std=std)
        else: torch.nn.init.trunc_normal_(noise, mean=0.0, std=std, a=-noise_clamp, b=noise_clamp)
        from functools import partial
        conditioned_flow = partial(self.flow_net, transformer_out)
        if self.flow_type == "lsd": decode = flm.lsd_decode
        elif self.flow_type == "flow_matching": decode = flm.ot_decode
        elif self.flow_type == "drifting": decode = flm.drifting_decode
        elif self.flow_type == "pointwise": decode = flm.pointwise_decode
        else: raise ValueError(self.flow_type)
        latent = decode(conditioned_flow, noise, sampler_decode_steps)
        return latent.to(backbone_dtype), out_eos
    flm.FlowLMModel.forward = fp16_forward
    model.flow_lm = model.flow_lm.half()
    model.flow_lm.flow_net = model.flow_lm.flow_net.float()
    model.flow_lm.out_eos = model.flow_lm.out_eos.float()
    def _encode_audio_dtype(self, audio):
        with torch.no_grad():
            latents = self.mimi.encode_to_latent(audio)
        w = self.flow_lm.speaker_proj_weight
        conditioning = F.linear(latents.to(w.dtype), w).to(self.flow_lm.input_linear.weight.dtype)
        return conditioning
    model._encode_audio = types.MethodType(_encode_audio_dtype, model)
    _orig_decode = model.mimi.decode_from_latent
    def decode_fp32(self, latent, mimi_state):
        return _orig_decode(latent.float(), mimi_state)
    model.mimi.decode_from_latent = types.MethodType(decode_fp32, model.mimi)

def bench(model, texts, bsizes, bursts=2):
    stream = BatchedStream(model, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
    stream.stream(texts[:4], max_frames=8)
    results = {}
    for b in bsizes:
        tts=[]
        for _ in range(bursts):
            torch.cuda.synchronize(); t0=time.perf_counter()
            stream.stream(texts[:b], max_frames=32)
            torch.cuda.synchronize(); tts.append(time.perf_counter()-t0)
        results[b]=sum(tts)/len(tts)
    return results

texts = make_texts(64)
m32 = TTSModel.load_model(config='config.yaml').to('cuda').eval(); m32.temp=0.3
r32 = bench(m32, texts, [1,8,16,32,48,64])
del m32; torch.cuda.empty_cache()
m16 = TTSModel.load_model(config='config.yaml').to('cuda').eval(); m16.temp=0.3
patch_fp16(m16)
r16 = bench(m16, texts, [1,8,16,32,48,64])
print('FP32', {k:round(v,3) for k,v in r32.items()})
print('FP16', {k:round(v,3) for k,v in r16.items()})
for b in r32: print(b, 'speedup', round(r32[b]/r16[b],3))
