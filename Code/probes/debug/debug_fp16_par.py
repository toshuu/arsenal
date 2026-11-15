import os, sys, torch, logging, types
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/kaggle/working/arsenal/Code')
os.chdir('/kaggle/working/arsenal/Code/model')
import torch.nn.functional as F
import pocket_tts.models.flow_lm as flm
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone

texts=["Hello, this is a short test sentence.","Good morning. The weather is nice today.","Testing one two three four five six seven eight nine ten."]
m = TTSModel.load_model(config="config.yaml").to("cuda").eval()
enable_fp16_backbone(m)
m.temp = 0.0
bs = BatchedStream(m, '/kaggle/working/arsenal/Code/probes/ref/voice.wav')
a1 = bs.stream([texts[0]], max_frames=32)[0].cpu()
a32 = bs.stream(texts*11, max_frames=32)[0].cpu()
print('b1vb32', float((a1-a32).abs().max()), float(torch.corrcoef(torch.stack([a1,a32]))[0,1]))
# compare two b1 runs
b1b = bs.stream([texts[0]], max_frames=32)[0].cpu()
print('b1vb1', float((a1-b1b).abs().max()))
