import sys, os, json, logging, time, traceback
sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
import torch
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts, pct, first_sound_ms
OUT='/kaggle/working/arsenal/Code/experiments/out'; os.makedirs(OUT,exist_ok=True)
VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'
variants=['english_18m_2026-10','english_18m_refl_2026-10','english_7m_2026-10','english_2m_2026-10']
out={'variants':[],'note':'English-only reference; not multilingual-safe for main path.'}
def measure(model,B=32,rounds=2):
    enable_fp16_backbone(model); model.temp=0.3
    sr=model.config.mimi.sample_rate; spf=int(round(sr/model.mimi.frame_rate))
    sp=BatchedStream(model,voice=VOICE,voice_seconds=4.0,max_first_tokens=16)
    prof=OUT+'/shrink_var_voice.pt'; sp.save_voice_profile(prof,conditioned=True)
    s=BatchedStream(model,voice_profile=prof,max_first_tokens=16,compact=True); texts=make_texts(B)
    s.stream(texts[:4],max_frames=4); torch.cuda.synchronize()
    all_ms=[]
    for rnd in range(rounds):
        bt=[texts[(rnd*13+r)%len(texts)] for r in range(B)]; ft=[[] for _ in range(B)]; t0=time.perf_counter()
        def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
        audio=s.stream(bt,on_chunk=cb); torch.cuda.synchronize()
        for r in range(B):
            ms=first_sound_ms(audio[r],ft[r],spf);
            if ms is not None: all_ms.append(ms)
    return {'B':B,'p50':round(pct(all_ms,50),2),'p95':round(pct(all_ms,95),2),'n':len(all_ms)}
for v in variants:
    rec={'variant':v}
    try:
        try:
            m=TTSModel.load_model(variant=v)
        except TypeError:
            try: m=TTSModel.load_model(model_name=v)
            except TypeError: m=TTSModel.load_model(v)
        m=m.to('cuda').eval(); rec['measure']=measure(m,32,2); rec['ok']=True
    except Exception as e:
        rec['ok']=False; rec['err']=str(e)[:300]
    out['variants'].append(rec); open(OUT+'/shrink_english_variants.json','w').write(json.dumps(out,indent=2))
    try: torch.cuda.empty_cache()
    except: pass
print('VARIANTS_DONE')
