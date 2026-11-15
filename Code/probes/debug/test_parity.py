import os, sys, torch, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
m=TTSModel.load_model(config='config.yaml').to('cuda').eval()
m.temp=0.0
bs=BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
texts=["Hello, this is a short test sentence.", "Good morning. The weather is nice today.", "Testing one two three four five six seven eight nine ten."]
F=12
single=bs.stream([texts[0]], max_frames=F)[0]
batch=bs.stream(texts, max_frames=F)
torch.cuda.synchronize()
print('b1 vs b3 row0 maxdiff', float((single-batch[0]).abs().max()), 'len', single.shape[0], batch[0].shape[0])
# inference single stream
st=m.get_state_for_audio_prompt('/kaggle/working/arsenal/Code/probes/ref/voice.wav')
chunks=[]
for ch in m.generate_audio_stream(st, texts[0]):
    chunks.append(ch)
    if sum(x.shape[0] for x in chunks)>=single.shape[0]: break
inf=torch.cat(chunks)[:single.shape[0]]
print('b1 vs inference maxdiff', float((single-inf).abs().max()))
