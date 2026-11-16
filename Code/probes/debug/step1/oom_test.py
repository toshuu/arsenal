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
try:
    model=TTSModel.load_model(config='config.yaml').to('cuda').eval()
    enable_fp16_backbone(model, mimi_fp16=True); load_fp16_weights(model, WEIGHTS)
    model.temp=0.3
    stream=BatchedStream(model, voice_profile=PROFILE, max_first_tokens=None, compact=True)
    # long texts: repeat "word " many times
    long = ("word " * 200).strip()
    texts=[long]*224
    stream.stream(texts, max_frames=300)
    torch.cuda.synchronize()
    print('OK')
except Exception as e:
    import traceback
    print('ERR', repr(e))
    traceback.print_exc()
