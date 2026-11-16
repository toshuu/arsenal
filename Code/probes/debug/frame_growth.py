import logging, os, sys, time
from pathlib import Path
import torch
REPO=Path('/kaggle/working/arsenal'); sys.path.insert(0,str(REPO/'Code')); os.chdir(REPO/'Code/model')
logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights
VOICE=REPO/'Code/probes/ref/voice.wav'
PROFILE=REPO/'Code/probes/out/voice_4s_cond.pt'
WEIGHTS=REPO/'Code/model/fp16_weights.pt'
model=TTSModel.load_model(config='config.yaml').to('cuda').eval()
enable_fp16_backbone(model, mimi_fp16=True); load_fp16_weights(model, WEIGHTS)
model.temp=0.3
stream=BatchedStream(model, voice_profile=PROFILE, max_first_tokens=16, compact=True, profile_steps=True)
texts=[f"Text {i} for testing." for i in range(224)]
for mf in (32,100,250):
    stream.stream(texts[:224], max_frames=8); torch.cuda.synchronize() # warm
    stream.stream(texts[:224], max_frames=mf); torch.cuda.synchronize()
    prof=stream.last_profile
    steps=prof['steps'] or 1
    print(mf, steps, round(prof['flow_ms']/steps,2), round(prof['mimi_ms']/steps,2), round(prof['emit_ms']/steps,2), round((prof['loop_ms'])/steps,2))
