import os, torch, logging
logging.disable(logging.CRITICAL)
os.chdir('/kaggle/working/arsenal/Code/model')
from pocket_tts import TTSModel
from pocket_tts.modules.stateful_module import init_states

torch.set_num_threads(1)
m=TTSModel.load_model(config='config.yaml').to('cuda').eval()
fl=m.flow_lm
ldim=fl.ldim; dim=fl.dim
T=100
torch.manual_seed(0)

def bench(fn, iters=20, warm=3):
    for _ in range(warm): fn()
    torch.cuda.synchronize()
    s=torch.cuda.Event(True); e=torch.cuda.Event(True)
    s.record()
    for _ in range(iters): fn()
    e.record(); torch.cuda.synchronize()
    return s.elapsed_time(e)/iters

for dtype in [torch.float32, torch.float16]:
    mm=m
    if dtype==torch.float16:
        mm=m.half()
    fl=mm.flow_lm; ldim=fl.ldim; dim=fl.dim
    print('dtype',dtype)
    for B in [1,4,8,16,32,64]:
        toks=torch.randint(0,100,(B,T),device='cuda')
        lat=torch.randn(B,1,ldim,device='cuda',dtype=dtype)
        ac=torch.empty(B,0,dim,device="cuda",dtype=dtype); bl=torch.empty(B,0,ldim,device="cuda",dtype=dtype); et=torch.empty(B,0,dtype=torch.int64,device="cuda")
        st=init_states(fl,B,T+2048)
        with torch.no_grad():
            pre=bench(lambda: mm._run_flow_lm_and_increment_step(st, text_tokens=toks, backbone_input_latents=bl, audio_conditioning=ac), iters=3)
        st=init_states(fl,B,T+2048)
        with torch.no_grad():
            mm._run_flow_lm_and_increment_step(st, text_tokens=toks, backbone_input_latents=bl, audio_conditioning=ac)
            step=bench(lambda: mm._run_flow_lm_and_increment_step(st, text_tokens=et, backbone_input_latents=lat, audio_conditioning=ac), iters=30)
        ms=init_states(mm.mimi,B,1024)
        mlat=torch.randn(B,1,32,device='cuda',dtype=dtype)
        with torch.no_grad():
            dec=bench(lambda: mm.mimi.decode_from_latent(mlat,ms), iters=20)
        print(f'B={B:3d} prefill100={pre:7.2f}ms step={step:7.2f}ms decode1frame={dec:7.2f}ms')
    if dtype==torch.float16:
        m=mm.float()
