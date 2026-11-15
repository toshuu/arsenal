import sys, os, json, logging, time
sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
import torch
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream, set_state_padding, _clone_state_to_batch
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts
from pocket_tts.modules.stateful_module import init_states, increment_steps
OUT='/kaggle/working/arsenal/Code/experiments/out'; os.makedirs(OUT,exist_ok=True)
def count(m):
    try: return sum(p.numel() for p in m.parameters())
    except: return None
model=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(model); model.temp=0.3
VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'; prof=OUT+'/shrink_comp_voice.pt'
sp0=BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16); sp0.save_voice_profile(prof, conditioned=True)
B=128; texts=make_texts(B); sp=BatchedStream(model, voice_profile=prof, voice_seconds=4.0, max_first_tokens=16, compact=True)
text_batch,text_pad,_=sp._build_text_batch(texts); vlen=sp._voice_state_len(); max_frames=12; seq_len=vlen+text_batch.shape[1]+max_frames+4
state=_clone_state_to_batch(sp.voice_state,B,seq_len,sp.device); set_state_padding(state,text_pad)
mimi_steps=int(model.mimi.encoder_frame_rate/model.mimi.frame_rate); mimi_state=init_states(model.mimi,B,(max_frames+4)*mimi_steps)
empty_tokens=torch.empty(B,0,dtype=torch.int64,device=sp.device); empty_latents=torch.empty(B,0,model.flow_lm.ldim,dtype=text_batch.dtype,device=sp.device)
model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=empty_latents,audio_conditioning=text_batch)
latent=model.flow_lm.bos_emb.view(1,1,-1).expand(B,1,-1); empty_audio=torch.empty(B,0,model.flow_lm.dim,dtype=text_batch.dtype,device=sp.device)
torch.cuda.synchronize(); t=time.perf_counter(); latent,_=model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=latent,audio_conditioning=empty_audio); torch.cuda.synchronize(); flow_ms=(time.perf_counter()-t)*1000
torch.cuda.synchronize(); t=time.perf_counter(); decode_input=latent*model.flow_lm.emb_std+model.flow_lm.emb_mean; _=model.mimi.decode_from_latent(decode_input,mimi_state); torch.cuda.synchronize(); mimi_ms=(time.perf_counter()-t)*1000
out={
  'params':{
    'flow_lm':count(model.flow_lm),'mimi':count(getattr(model,'mimi',None)),'total':count(model),
    'mimi_encoder':count(getattr(model.mimi,'encoder',None)),'mimi_decoder':count(getattr(model.mimi,'decoder',None))
  },
  'timing_B128_ms':{'flow_step':round(flow_ms,2),'mimi_decode':round(mimi_ms,2)},
  'note':'Decoder shrink highest leverage for multilingual (decode-bound at B). English small models reference only.'
}
open(OUT+'/shrink_components.json','w').write(json.dumps(out,indent=2)); print('COMP_DONE')
