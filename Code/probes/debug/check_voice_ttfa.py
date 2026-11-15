import os,sys,logging,time
from pathlib import Path
import torch
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'Code')); os.chdir(REPO/'Code/model'); logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
VOICE=REPO/'Code/probes/ref/voice.wav'
m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(m); m.temp=0.3
texts=[f"The old sailor found a brass key near the harbor number {i}." for i in range(96)]
streams={s:BatchedStream(m,VOICE,voice_seconds=s,max_first_tokens=16) for s in (4.0,3.0,2.0)}
for s,st in streams.items(): print('frames',s,st.voice.shape[1])
for s,st in streams.items(): st.stream(texts[:4],max_frames=4)
torch.cuda.synchronize()
res={s:[] for s in streams}
for rnd in range(6):
    for s in (4.0,3.0,2.0):
        st=streams[s]; t={}
        def cb(row,chunk,elapsed):
            if row==0 and 'x' not in t: t['x']=time.perf_counter()
        t0=time.perf_counter(); st.stream(texts[:96],on_chunk=cb); torch.cuda.synchronize()
        res[s].append((t['x']-t0)*1000)
for s,v in res.items(): print(s,[round(x,1) for x in v])
