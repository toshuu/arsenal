import os, sys, torch, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
m=TTSModel.load_model(config='config.yaml').to('cuda').eval(); m.temp=0.0
bs=BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
text="Hello, this is a short test sentence."
b=bs.stream([text], max_frames=3)[0]
st=m.get_state_for_audio_prompt('/kaggle/working/arsenal/Code/probes/ref/voice.wav')
ch=[]
for x in m.generate_audio_stream(st,text):
    ch.append(x)
    if len(ch)>=3: break
i=torch.cat(ch)
print('b shape',b.shape,'i shape',i.shape)
print('b stats',float(b.mean()),float(b.std()),float(b.abs().max()))
print('i stats',float(i.mean()),float(i.std()),float(i.abs().max()))
for k in range(3):
    bb=b[k*1920:(k+1)*1920]; ii=i[k*1920:(k+1)*1920]
    print(k,'maxdiff',float((bb-ii).abs().max()),'corr',float(torch.corrcoef(torch.stack([bb,ii]))[0,1]) if bb.std()>0 and ii.std()>0 else None)
print('b first frame nz', int((b[:1920].abs()>0.01).sum()), 'i', int((i[:1920].abs()>0.01).sum()))
print('b samples', [round(float(x),4) for x in b[100:110]])
print('i samples', [round(float(x),4) for x in i[100:110]])
# compare latents via batch internal? monkeypatch decode to capture
