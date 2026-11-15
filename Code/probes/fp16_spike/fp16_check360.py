import os, sys, time, torch, logging, types
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
sys.path.insert(0, '/kaggle/working/arsenal/Code/probes')
os.chdir('/kaggle/working/arsenal/Code/model')
import torch.nn.functional as F
import pocket_tts.models.flow_lm as flm
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from bench_batch_server import make_texts, pct, first_sound_ms

def patch_fp16(model):
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
        noise = torch.empty(noise_shape, dtype=torch.float32, device=transformer_out.device)
        if noise_clamp is None: torch.nn.init.normal_(noise, mean=0.0, std=std)
        else: torch.nn.init.trunc_normal_(noise, mean=0.0, std=std, a=-noise_clamp, b=noise_clamp)
        from functools import partial
        conditioned_flow = partial(self.flow_net, transformer_out)
        decode = {'lsd':flm.lsd_decode,'flow_matching':flm.ot_decode,'drifting':flm.drifting_decode,'pointwise':flm.pointwise_decode}[self.flow_type]
        latent = decode(conditioned_flow, noise, sampler_decode_steps)
        return latent.to(backbone_dtype), out_eos
    flm.FlowLMModel.forward = fp16_forward
    model.flow_lm = model.flow_lm.half()
    model.flow_lm.flow_net = model.flow_lm.flow_net.float()
    model.flow_lm.out_eos = model.flow_lm.out_eos.float()
    def _encode_audio_dtype(self, audio):
        with torch.no_grad(): latents = self.mimi.encode_to_latent(audio)
        w = self.flow_lm.speaker_proj_weight
        return F.linear(latents.to(w.dtype), w).to(self.flow_lm.input_linear.weight.dtype)
    model._encode_audio = types.MethodType(_encode_audio_dtype, model)
    _orig_decode = model.mimi.decode_from_latent
    def decode_fp32(self, latent, mimi_state): return _orig_decode(latent.float(), mimi_state)
    model.mimi.decode_from_latent = types.MethodType(decode_fp32, model.mimi)

m = TTSModel.load_model(config='config.yaml').to('cuda').eval(); m.temp=0.3
patch_fp16(m)
stream = BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
spf = int(round(m.config.mimi.sample_rate / m.config.mimi.frame_rate))
texts = make_texts(128)
stream.stream(texts[:4], max_frames=8); torch.cuda.synchronize()
print(' B   p50    p95    max  under360   RTF   MB')
for b in [64,72,80,88,96]:
    try:
        all_first=[]; rtf=[]
        for burst in range(3):
            batch_texts=[texts[(burst*7+r)%len(texts)] for r in range(b)]
            ft=[[] for _ in range(b)]; fn=[0]*b; t0=time.perf_counter()
            def cb(row,chunk,elapsed):
                if row==0 and fn[row]<5: torch.cuda.synchronize()
                ft[row].append(time.perf_counter()-t0); fn[row]+=1
            torch.cuda.reset_peak_memory_stats()
            audio=stream.stream(batch_texts,on_chunk=cb)
            torch.cuda.synchronize(); w=time.perf_counter()-t0
            a_s=sum(a.numel() for a in audio)/m.config.mimi.sample_rate
            rtf.append(w/a_s if a_s else 0)
            for r in range(b):
                fs=first_sound_ms(audio[r],ft[r],spf)
                if fs is not None: all_first.append(fs)
        mb=torch.cuda.max_memory_allocated()/1e6
        u=sum(1 for x in all_first if x<=360)
        print(f'{b:3d} {pct(all_first,50):6.1f} {pct(all_first,95):6.1f} {max(all_first):6.1f} {u:>3}/{len(all_first):<3} {pct(rtf,50):6.3f} {mb:6.0f}', flush=True)
    except Exception as e:
        print(f'{b:3d} ERR {e}', flush=True)
        torch.cuda.empty_cache()
        break
