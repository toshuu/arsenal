import sys, os, json, logging, time, traceback, copy
sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
OUT='/kaggle/working/arsenal/Code/experiments/out'; os.makedirs(OUT,exist_ok=True)
import torch, scipy.io.wavfile
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts, pct, first_sound_ms
VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'
res={'attempts':[]}
variants=['english_2m_2026-10','english_7m_2026-10','english_18m_2026-10']
base=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(base); base.temp=0.3
texts=make_texts(8)
def run_test(label, model, wav_name):
    sr=model.config.mimi.sample_rate; spf=int(round(sr/model.mimi.frame_rate))
    sp=BatchedStream(model,voice=VOICE,voice_seconds=4.0,max_first_tokens=16)
    prof=OUT+'/swap_voice.pt'; sp.save_voice_profile(prof,conditioned=True)
    s=BatchedStream(model,voice_profile=prof,max_first_tokens=16,compact=True)
    s.stream(texts[:2],max_frames=4); torch.cuda.synchronize()
    all_ms=[]; ft=[[] for _ in range(len(texts))]; t0=time.perf_counter()
    def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
    audio=s.stream(texts,on_chunk=cb); torch.cuda.synchronize(); wall=time.perf_counter()-t0
    for r in range(len(texts)):
        ms=first_sound_ms(audio[r],ft[r],spf)
        if ms is not None: all_ms.append(ms)
    a=audio[0].detach().float().cpu().numpy(); scipy.io.wavfile.write(os.path.join(OUT,wav_name), sr, a)
    return {'p50':round(pct(all_ms,50),2) if all_ms else None,'p95':round(pct(all_ms,95),2) if all_ms else None,'wall':round(wall,3),'n':len(all_ms),'wav':wav_name}

try: res['baseline']=run_test('baseline', base, 'swapfix_baseline.wav')
except Exception as e: res['baseline_err']=str(e)

for v in variants:
    rec={'variant':v}
    try:
        small=TTSModel.load_model(language=v).to('cuda').eval()
        m=copy.deepcopy(base)
        sm=copy.deepcopy(small.mimi).to(m.device).eval()
        # match backbone dtype/path: try fp16
        try: sm=sm.half()
        except Exception: pass
        m.mimi=sm
        rec['mimi_params']=sum(p.numel() for p in m.mimi.parameters())
        rec['measure']=run_test(v,m,f'swapfix_{v}.wav')
        rec['ok']=True
    except Exception as e:
        rec['ok']=False; rec['err']=str(e)[:400]; rec['tb']=traceback.format_exc(limit=3)
    res['attempts'].append(rec)
    open(OUT+'/swap_mimi_fix.json','w').write(json.dumps(res,indent=2))
    try: torch.cuda.empty_cache()
    except: pass
print('SWAPFIX_DONE')
