import argparse, os, sys, wave
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Code'))
from batch.call_chunker import split_call_text
from batch.server import Settings, TTSEngine
TEXTS = [
    "Hello, this is a call from Arsenal. The line is clear. Can you hear me now?",
    "Please read the first sentence. Then continue to the next one. Keep the audio smooth.",
    "The quick brown fox jumps over the lazy dog. Pack my box with five dozen jugs. The sun is bright.",
    "Namaste, this is a short test. The voice should stay the same. The joins should be smooth.",
    "One two three four five. Six seven eight nine ten. Eleven twelve thirteen fourteen fifteen.",
]
def write_wav(path, samples, rate=24000):
    data=np.clip(np.asarray(samples,dtype='float32'),-1.0,1.0)
    pcm=(data*32767.0).astype('<i2').tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path),'wb') as h:
        h.setnchannels(1); h.setsampwidth(2); h.setframerate(rate); h.writeframes(pcm)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--profile',default='v1')
    ap.add_argument('--out',default=str(ROOT/'Code/probes/out/call_mode'))
    ap.add_argument('--frames',default='16')
    args=ap.parse_args()
    profile_path=ROOT/'Code/probes/out/voice_4s_cond.pt'
    os.environ.setdefault('ARSENAL_VOICE_PROFILES',f'v1={profile_path}')
    os.environ.setdefault('ARSENAL_MODEL_DIR',str(ROOT/'Code/model'))
    engine=TTSEngine(Settings()); engine.load()
    stream=engine._stream_for(args.profile)
    out_dir=Path(args.out)
    for mf in [int(x) for x in args.frames.split(',') if x.strip()]:
        for i,text in enumerate(TEXTS):
            chunks=split_call_text(stream,text,mf)
            parts=[]
            for chunk in chunks:
                audio=engine.synthesize([chunk], max_frames=mf, profile_id=args.profile)
                parts.append(audio[0].detach().float().cpu().numpy())
            joined=np.concatenate(parts) if parts else np.zeros(0,dtype='float32')
            path=out_dir/f'call_mf{mf}_{i}.wav'; write_wav(path,joined)
            print({'file':str(path),'mf':mf,'chunks':len(chunks),'samples':int(joined.size),'seconds':round(float(joined.size)/24000.0,3)})
if __name__=='__main__': main()
