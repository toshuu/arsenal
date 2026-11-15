import os, torch, logging
logging.disable(logging.CRITICAL)
os.chdir('/kaggle/working/arsenal/Code/model')
from pocket_tts import TTSModel
from pocket_tts.modules.stateful_module import init_states, increment_steps
torch.set_num_threads(1)
m=TTSModel.load_model(config='config.yaml').to('cuda').eval()
fl=m.flow_lm; B=32; T=100; ldim=fl.ldim; dim=fl.dim
st=init_states(fl,B,T+256)
toks=torch.randint(0,100,(B,T),device='cuda')
ac=torch.empty(B,0,dim,device='cuda'); bl=torch.empty(B,0,ldim,device='cuda')
et=torch.empty(B,0,dtype=torch.int64,device='cuda')
lat=torch.randn(B,1,ldim,device='cuda')
with torch.no_grad():
    m._run_flow_lm_and_increment_step(st, text_tokens=toks, backbone_input_latents=bl, audio_conditioning=ac)
    for _ in range(5): m._run_flow_lm_and_increment_step(st, text_tokens=et, backbone_input_latents=lat, audio_conditioning=ac)
    torch.cuda.synchronize()
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]) as p:
        for _ in range(10): m._run_flow_lm_and_increment_step(st, text_tokens=et, backbone_input_latents=lat, audio_conditioning=ac)
        torch.cuda.synchronize()
print(p.key_averages().table(sort_by='self_cuda_time_total', row_limit=20))
print('--- increment_steps only ---')
s=torch.cuda.Event(True); e=torch.cuda.Event(True); s.record()
for _ in range(1000): increment_steps(fl, st, increment=1)
e.record(); torch.cuda.synchronize(); print('per call ms', s.elapsed_time(e)/1000)
