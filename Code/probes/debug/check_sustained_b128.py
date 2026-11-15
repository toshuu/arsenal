import os,sys,logging,time,json
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
st=BatchedStream(m,VOICE,voice_seconds=3.0,max_first_tokens=16)
st.stream(texts[:4],max_frames=4); torch.cuda.synchronize()
print('burst p50 p95 under wall vram')
for i in range(6):
    ft=[[] for _ in range(128)]; t0=time.perf_counter()
    def cb(row,chunk,elapsed): ft[row].append(time.perf_counter()-t0)
    torch.cuda.reset_peak_memory_stats()
    audio=st.stream(texts[:128],on_chunk=cb); torch.cuda.synchronize()
    wall=time.perf_counter()-t0
    ms=[first_sound_ms(audio[r],ft[r],spf) for r in range(128)]
    ms=[x for x in ms if x is not None]
    print(i,round(pct(ms,50),1),round(pct(ms,95),1),sum(1 for x in ms if x<=350),round(wall,2),round(torch.cuda.max_memory_allocated()/1e6))
