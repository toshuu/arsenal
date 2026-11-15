import os,sys,logging
from pathlib import Path
import torch
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'Code')); os.chdir(REPO/'Code/model'); logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
VOICE=REPO/'Code/probes/ref/voice.wav'
m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); m.temp=0.0
TEXT="The quick brown fox jumps over the lazy dog."
for s in (6.5,4.0,3.0,2.0):
    st=BatchedStream(m,VOICE,voice_seconds=s,max_first_tokens=16)
    chunks=[]
    def cb(row,chunk,elapsed):
        if row==0: chunks.append(float(chunk.abs().max()))
    st.stream([TEXT],on_chunk=cb)
    print(s,'frame_peak_first6',[round(x,4) for x in chunks[:6]])
