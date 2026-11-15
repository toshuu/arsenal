import sys, os, json, logging, time
sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
import torch
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream, set_state_padding, _clone_state_to_batch
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts
from pocket_tts.modules.stateful_module import init_states, increment_steps
OUT='/kaggle/working/arsenal/Code/experiments/out'
os.makedirs(OUT,exist_ok=True)
def sync(): torch.cuda.synchronize()
model=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(model); model.temp=0.3
VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'; prof=OUT+'/shrink_cur_voice.pt'
sp0=BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16); sp0.save_voice_profile(prof, conditioned=True)
out=[]
for B in [32,128]:
    texts=make_texts(B); sp=BatchedStream(model, voice_profile=prof, voice_seconds=4.0, max_first_tokens=16, compact=True)
    sync(); t_all=time.perf_counter(); text_batch,text_pad,token_counts=sp._build_text_batch(texts); sync(); t_text=time.perf_counter()
    vlen=sp._voice_state_len(); max_frames=20; seq_len=vlen+text_batch.shape[1]+max_frames+4
    state=_clone_state_to_batch(sp.voice_state,B,seq_len,sp.device); set_state_padding(state,text_pad)
    mimi_steps=int(model.mimi.encoder_frame_rate/model.mimi.frame_rate); mimi_state=init_states(model.mimi,B,(max_frames+4)*mimi_steps); sync(); t_state=time.perf_counter()
    empty_tokens=torch.empty(B,0,dtype=torch.int64,device=sp.device); empty_latents=torch.empty(B,0,model.flow_lm.ldim,dtype=text_batch.dtype,device=sp.device)
    model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=empty_latents,audio_conditioning=text_batch); sync(); t_cond=time.perf_counter()
    latent=model.flow_lm.bos_emb.view(1,1,-1).expand(B,1,-1); empty_audio=torch.empty(B,0,model.flow_lm.dim,dtype=text_batch.dtype,device=sp.device)
    sync(); t=time.perf_counter(); latent,is_eos=model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=latent,audio_conditioning=empty_audio); sync(); flow0=(time.perf_counter()-t)*1000
    sync(); t=time.perf_counter(); decode_input=latent*model.flow_lm.emb_std+model.flow_lm.emb_mean; _=model.mimi.decode_from_latent(decode_input,mimi_state); increment_steps(model.mimi,mimi_state,increment=mimi_steps); sync(); mimi0=(time.perf_counter()-t)*1000; t_first=time.perf_counter()
    step_ms=[]; dec_ms=[]
    for i in range(1,8):
        sync(); t=time.perf_counter(); latent,is_eos=model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=latent,audio_conditioning=empty_audio); sync(); step_ms.append((time.perf_counter()-t)*1000)
        sync(); t=time.perf_counter(); decode_input=latent*model.flow_lm.emb_std+model.flow_lm.emb_mean; _=model.mimi.decode_from_latent(decode_input,mimi_state); increment_steps(model.mimi,mimi_state,increment=mimi_steps); sync(); dec_ms.append((time.perf_counter()-t)*1000)
    out.append({'B':B,'prep_text_ms':round((t_text-t_all)*1000,2),'state_ms':round((t_state-t_text)*1000,2),'cond_ms':round((t_cond-t_state)*1000,2),'flow0_ms':round(flow0,2),'mimi0_ms':round(mimi0,2),'ttfa_compute_ms':round((t_first-t_all)*1000,2),'flow_avg_ms':round(sum(step_ms)/len(step_ms),2),'mimi_avg_ms':round(sum(dec_ms)/len(dec_ms),2)})
open(OUT+'/shrink_current_breakdown.json','w').write(json.dumps(out,indent=2)); print('BREAKDOWN_DONE')
