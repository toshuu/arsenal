import os,sys,logging
from pathlib import Path
import numpy as np, torch, soundfile as sf
REPO=Path('/kaggle/working/arsenal')
sys.path.insert(0,str(REPO/'Code')); sys.path.insert(0,str(REPO/'Code'/'probes'))
os.chdir(REPO/'Code'/'model'); logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
import batch.batched_stream as bsm

VOICE=REPO/'Code'/'probes'/'ref'/'voice.wav'
TEXT="The quick brown fox jumps over the lazy dog near the river bank."
m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); m.temp=0.0
st=m.get_state_for_audio_prompt(str(VOICE))
ref=m.generate_audio(st,TEXT).cpu().numpy().reshape(-1)
bsm.increment_steps=lambda *a,**k: None
bat=bsm.BatchedStream(m,VOICE).stream([TEXT])[0].cpu().numpy().reshape(-1)
n=min(len(ref),len(bat))
print('OLD (no increment) corr', float(np.corrcoef(ref[:n],bat[:n])[0,1]))
def c(x):
    X=np.abs(np.fft.rfft(x*np.hanning(len(x))));fr=np.fft.rfftfreq(len(x),1/24000)
    return (X*fr).sum()/X.sum(),(X[fr>6000]**2).sum()/(X**2).sum()
print('ref centroid/hi',c(ref)); print('old centroid/hi',c(bat))
d=REPO/'Code'/'probes'/'out'/'audio_fixcmp';d.mkdir(parents=True,exist_ok=True)
sf.write(d/'batched_before.wav',bat,24000)
