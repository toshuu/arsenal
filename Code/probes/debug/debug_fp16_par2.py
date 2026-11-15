import os, sys, torch, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
texts=["Hello, this is a short test sentence."] + ["Good morning. The weather is nice today."]*31
m = TTSModel.load_model(config="config.yaml").to("cuda").eval()
enable_fp16_backbone(m); m.temp=0.0
bs = BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
a1 = bs.stream([texts[0]], max_frames=32)[0].cpu()
a32 = bs.stream(texts, max_frames=32)[0].cpu()
print('maxdiff', float((a1-a32).abs().max()))
print('corr', float(torch.corrcoef(torch.stack([a1,a32]))[0,1]))
