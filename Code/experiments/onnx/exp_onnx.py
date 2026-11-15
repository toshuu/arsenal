"""Sideline ONNX experiment: attempt exports + ORT micro gain. Writes incremental results."""
import os, sys, json, time, logging
logging.disable(logging.CRITICAL)
os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF','expandable_segments:True')
OUT=os.path.join(os.path.dirname(__file__),'..','out'); os.makedirs(OUT,exist_ok=True)
SUM=os.path.join(OUT,'onnx_summary.json')
def save(d):
    tmp=SUM+'.tmp'; open(tmp,'w').write(json.dumps(d,indent=2)); os.replace(tmp,SUM)
res={'ort_available':False,'dummy_export':'n/a','dummy_ort_ms':None,'full_export_error':None,'gain_note':None,'sample_audio':None,'notes':[]}
try:
    import onnxruntime as ort, numpy as np
    res['ort_available']=True; res['ort_providers']=ort.get_available_providers()
except Exception as e:
    res['notes'].append(f'onnxruntime missing: {e}'); save(res); print('ONNX_DONE',json.dumps(res)); sys.exit(0)
try:
    import torch, torch.nn as nn
    class D(nn.Module):
        def __init__(self): super().__init__(); self.l=nn.Linear(4,4)
        def forward(self,x): return self.l(x)
    d=D().eval(); x=torch.randn(1,4); path=os.path.join(OUT,'dummy.onnx')
    torch.onnx.export(d,x,path,input_names=['x'],output_names=['y'],opset_version=17,dynamo=False)
    res['dummy_export']='ok'; res['dummy_path']=path
    sess=ort.InferenceSession(path, providers=['CUDAExecutionProvider','CPUExecutionProvider'])
    x=np.random.randn(1,4).astype(np.float32)
    for _ in range(50): sess.run(None,{'x':x})
    t=time.perf_counter()
    for _ in range(500): sess.run(None,{'x':x})
    res['dummy_ort_ms']=round((time.perf_counter()-t)/500*1000,4)
    res['ort_session_providers']=sess.get_providers()
    save(res)
    # full export attempt
    sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
    os.chdir('/kaggle/working/arsenal/Code/model')
    from pocket_tts import TTSModel
    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from pocket_tts.modules.stateful_module import init_states
    from bench_batch_server import make_texts
    m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(m); m.temp=0.0
    sp=BatchedStream(m, voice='/kaggle/working/arsenal/Code/probes/ref/voice.wav', voice_seconds=4.0, max_first_tokens=16)
    texts=make_texts(4); prefix,pad,_=sp._build_prefixes(texts[:4])
    state=init_states(m.flow_lm,4,prefix.shape[1]+40)
    from batch.batched_stream import set_state_padding; set_state_padding(state,pad)
    names=list(state.keys())
    class FlowStep(torch.nn.Module):
        def __init__(self,model,names): super().__init__(); self.m=model; self.names=names
        def forward(self, text_tokens, latent, audio_cond, *flat):
            st={}; i=0
            for n in self.names: st[n]={'offset':flat[i],'pad':flat[i+1],'cache':flat[i+2]}; i+=3
            out,eos=self.m._run_flow_lm_and_increment_step(st,text_tokens,latent,audio_cond)
            outs=[out,eos]
            for n in self.names: outs.extend([st[n]['offset'],st[n]['pad'],st[n]['cache']])
            return tuple(outs)
    wrap=FlowStep(m,names).eval()
    flat=[]
    for n in names:
        for k in ['offset','pad','cache']: flat.append(state[n][k])
    empty_tokens=torch.empty(4,0,dtype=torch.int64,device='cuda')
    latent=m.flow_lm.bos_emb.view(1,1,-1).expand(4,1,-1)
    try:
        torch.export.export(wrap,(empty_tokens,latent,prefix)+tuple(flat))
        res['full_export_error']=None
    except Exception as e:
        res['full_export_error']=f'{type(e).__name__}: {str(e)[:300]}'
    res['gain_note']='No end-to-end ONNX gain: full flow/mimi export blocked by stateful dict API + data-dependent cache guards. ORT micro-bench on dummy op only.'
    res['sample_audio']=None
    res['notes'].append('Full stateful streaming export needs API/state refactor (tensorized state, static control flow).')
except Exception as e:
    res['notes'].append(f'err: {e}')
save(res); print('ONNX_DONE',json.dumps(res))
