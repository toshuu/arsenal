import os,sys,logging,time
from pathlib import Path
import torch
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'Code')); sys.path.insert(0,str(REPO/'Code'/'probes')); os.chdir(REPO/'Code/model'); logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts,pct,first_sound_ms
VOICE=REPO/'Code/probes/ref/voice.wav'
m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(m); m.temp=0.3
sr=m.config.mimi.sample_rate; spf=int(round(sr/m.mimi.frame_rate)); texts=make_texts(128)
cfgs={'3.0/16':(3.0,16),'3.0/24':(3.0,24),'4.0/16':(4.0,16),'4.0/24':(4.0,24)}
st={k:BatchedStream(m,VOICE,voice_seconds=v,max_first_tokens=c) for k,(v,c) in cfgs.items()}
for s in st.values(): s.stream(texts[:4],max_frames=4)
torch.cuda.synchronize(); B=96
res={k:[] for k in st}
for rnd in range(5):
  for k in (['3.0/16','4.0/16','3.0/24','4.0/24'] if rnd%2==0 else ['4.0/24','3.0/24','4.0/16','3.0/16']):
    ft=[[] for _ in range(B)]; t0=time.perf_counter()
    def cb(row,chunk,elapsed): ft[row].append(time.perf_counter()-t0)
    audio=st[k].stream(texts[:B],on_chunk=cb); torch.cuda.synchronize()
    ms=[first_sound_ms(audio[r],ft[r],spf) for r in range(B)]; ms=[x for x in ms if x is not None]
    res[k].append((pct(ms,50),pct(ms,95),sum(1 for x in ms if x<=350)))
for k,v in res.items():
  print(k,'p50s',[round(x[0]) for x in v],'p95s',[round(x[1]) for x in v],'pass',[x[2] for x in v])
