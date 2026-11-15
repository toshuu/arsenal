import os, sys, time, torch, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
m=TTSModel.load_model(config='config.yaml').to('cuda').eval()
bs=BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
texts=["Hello, this is a short test sentence.", "Good morning. The weather is nice today.", "Testing one two three four five six seven eight nine ten."]
for _ in range(1):
    bs.stream(texts[:2], max_frames=12)
torch.cuda.synchronize()
first={}
def cb(row, chunk, t):
    if row not in first and float(chunk.abs().max())>0.01: first[row]=t
t0=time.perf_counter(); out=bs.stream(texts, on_chunk=cb, max_frames=12); wall=time.perf_counter()-t0
print('wall', round(wall*1000,1), 'first_ms', {k:round(v*1000,1) for k,v in sorted(first.items())})
print('shapes', [int(x.shape[0]) for x in out])
