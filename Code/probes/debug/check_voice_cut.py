import os,sys,logging
from pathlib import Path
import torch
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'Code')); os.chdir(REPO/'Code/model'); logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from pocket_tts.data.audio import audio_read
from pocket_tts.data.audio_utils import convert_audio,end_on_pause
from batch.batched_stream import BatchedStream
VOICE=REPO/'Code/probes/ref/voice.wav'
m=TTSModel.load_model(config='config.yaml').to('cuda').eval()
sr=m.config.mimi.sample_rate
audio0,sr0=audio_read(VOICE)
audio0=convert_audio(audio0,sr0,sr,1)
print('raw seconds',audio0.shape[-1]/sr)
for s in (6.5,4.0,3.0,2.0):
    cur=BatchedStream(m,VOICE,voice_seconds=s).voice.shape[1]
    a=audio0[..., :int(s*sr)]
    a=end_on_pause(a,sr)
    with torch.no_grad():
        p=m._encode_audio(a.unsqueeze(0).to('cuda'))
    if m.flow_lm.insert_bos_before_voice:
        p=torch.cat([m.flow_lm.bos_before_voice,p],dim=1)
    print(f"voice {s}: cut-then-pause frames={p.shape[1]} pause_len={a.shape[-1]/sr:.3f} current_frames={cur}")
