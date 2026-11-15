import os,sys,logging
from pathlib import Path
import numpy as np, torch, soundfile as sf
REPO=Path('/kaggle/working/arsenal')
sys.path.insert(0,str(REPO/'Code')); sys.path.insert(0,str(REPO/'Code'/'probes'))
os.chdir(REPO/'Code'/'model'); logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream

VOICE=REPO/'Code'/'probes'/'ref'/'voice.wav'
TEXT="The quick brown fox jumps over the lazy dog near the river bank."

m=TTSModel.load_model(config='config.yaml').to('cuda').eval()
m.temp=0.0
st=m.get_state_for_audio_prompt(str(VOICE))
ref=m.generate_audio(st,TEXT).cpu().numpy().reshape(-1)
bs=BatchedStream(m,VOICE)
bat=bs.stream([TEXT])[0].cpu().numpy().reshape(-1)

def stats(x,name):
    X=np.abs(np.fft.rfft(x*np.hanning(len(x)))); fr=np.fft.rfftfreq(len(x),1/24000)
    e=(X**2).sum()
    print(f"{name:12s} dur={len(x)/24000:.2f}s rms={np.sqrt((x**2).mean()):.4f} centroid={(X*fr).sum()/X.sum():.0f}Hz >6kfrac={(X[fr>6000]**2).sum()/e:.4f}")
stats(ref,'ref'); stats(bat,'batched')
n=min(len(ref),len(bat)); r=ref[:n]; b=bat[:n]
print('corr', float(np.corrcoef(r,b)[0,1]))
d=REPO/'Code'/'probes'/'out'/'audio_fixcmp'; d.mkdir(parents=True,exist_ok=True)
sf.write(d/'ref.wav',ref,24000); sf.write(d/'batched_fixed.wav',bat,24000)
print('wrote',d)
