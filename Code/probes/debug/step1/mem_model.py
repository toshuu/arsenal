import logging, os, sys
from pathlib import Path
import torch
REPO=Path('/kaggle/working/arsenal'); sys.path.insert(0,str(REPO/'Code')); os.chdir(REPO/'Code/model')
logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights
from pocket_tts.modules.stateful_module import init_states
VOICE=REPO/'Code/probes/ref/voice.wav'
PROFILE=REPO/'Code/probes/out/voice_4s_cond.pt'
WEIGHTS=REPO/'Code/model/fp16_weights.pt'
import gc
for mf in [100,150,200,250]:
    gc.collect(); torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
    model=TTSModel.load_model(config='config.yaml').to('cuda').eval()
    enable_fp16_backbone(model, mimi_fp16=True); load_fp16_weights(model, WEIGHTS)
    model.temp=0.3
    # mimic stream init
    from batch.batched_stream import BatchedStream as BS
    stream = BS(model, voice_profile=PROFILE, max_first_tokens=16)
    # force init like stream
    import time
    torch.cuda.reset_peak_memory_stats()
    before = torch.cuda.memory_allocated()/2**20
    try:
        texts=["hi"]*224
        # run with max_frames
        stream.stream(texts, max_frames=mf)
    except Exception as e:
        pass
    peak = torch.cuda.max_memory_allocated()/2**20
    res = torch.cuda.memory_reserved()/2**20
    print('mf',mf,'peak_alloc_mb',round(peak,1),'reserved_mb',round(res,1),'delta',round(peak-before,1))
    del model, stream
    gc.collect(); torch.cuda.empty_cache()
