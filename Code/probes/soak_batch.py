import argparse, json, logging, os, sys, time
from pathlib import Path
import torch
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
sys.path.insert(0, str(REPO / "Code" / "probes"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel  # noqa: E402
from batch.batched_stream import BatchedStream  # noqa: E402
from batch.fp16 import enable_fp16_backbone  # noqa: E402
from bench_batch_server import make_texts, pct, first_sound_ms  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--b", type=int, default=128)
ap.add_argument("--minutes", type=int, default=15)
ap.add_argument("--voice", default=str(REPO / "Code/probes/ref/voice.wav"))
ap.add_argument("--profile", default=str(REPO / "Code/probes/out/voice_4s_cond_soak.pt"))
ap.add_argument("--out", default=str(REPO / "Code/probes/out/soak.jsonl"))
ap.add_argument("--summary", default=str(REPO / "Code/probes/out/soak_summary.json"))
args = ap.parse_args()

OUT = Path(args.out); SUM = Path(args.summary)
OUT.parent.mkdir(parents=True, exist_ok=True)
model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
enable_fp16_backbone(model); model.temp = 0.3
sr = model.config.mimi.sample_rate
spf = int(round(sr / model.mimi.frame_rate))
texts = make_texts(max(args.b, 160))
base = BatchedStream(model, voice=args.voice, voice_seconds=4.0, max_first_tokens=16)
Path(args.profile).parent.mkdir(parents=True, exist_ok=True)
base.save_voice_profile(args.profile, conditioned=True)
stream = BatchedStream(model, voice_profile=args.profile, max_first_tokens=16, compact=True)
stream.stream(texts[:4], max_frames=4); torch.cuda.synchronize()

start = time.perf_counter(); duration = args.minutes * 60
burst = 0; p95s=[]; rtfs=[]; req=0; under=0; errors=0; oom=0
with open(OUT, 'w') as f:
    while time.perf_counter() - start < duration:
        bt = [texts[(burst * 13 + r) % len(texts)] for r in range(args.b)]
        ft=[[] for _ in range(args.b)]; t0=time.perf_counter()
        def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
        try:
            audio=stream.stream(bt,on_chunk=cb); torch.cuda.synchronize()
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache(); oom+=1; errors+=1
            f.write(json.dumps({"burst":burst,"error":"oom"})+"\n"); f.flush(); burst+=1; continue
        except Exception as e:
            errors+=1; f.write(json.dumps({"burst":burst,"error":str(e)})+"\n"); f.flush(); burst+=1; continue
        wall=time.perf_counter()-t0
        ms=[first_sound_ms(audio[r],ft[r],spf) for r in range(args.b)]
        ms=[x for x in ms if x is not None]
        audio_s=sum(a.numel() for a in audio)/sr
        rtf=wall/audio_s if audio_s else None
        p95=pct(ms,95) if ms else None
        u=sum(1 for x in ms if x<=350)
        req+=len(ms); under+=u
        if p95 is not None: p95s.append(p95)
        if rtf is not None: rtfs.append(rtf)
        rec={"burst":burst,"p95":round(p95,2) if p95 else None,"under":u,"n":len(ms),"rtf":round(rtf,4) if rtf else None,"wall":round(wall,3)}
        f.write(json.dumps(rec)+"\n"); f.flush()
        if burst % 20 == 0:
            print(f"burst={burst} p95={rec['p95']} under={u}/{len(ms)} rtf={rec['rtf']} elapsed={time.perf_counter()-start:.0f}s", flush=True)
        burst += 1
elapsed=time.perf_counter()-start
agg={"B":args.b,"duration_s":round(elapsed,1),"bursts":burst,"requests":req,"under350":under,
     "under350_pct":round(100*under/req,3) if req else None,
     "burst_p95_median":round(pct(p95s,50),2) if p95s else None,
     "burst_p95_p95":round(pct(p95s,95),2) if p95s else None,
     "burst_p95_max":round(max(p95s),2) if p95s else None,
     "bursts_p95_gt350":sum(1 for x in p95s if x>350) if p95s else None,
     "rtf_median":round(pct(rtfs,50),4) if rtfs else None,
     "rtf_p95":round(pct(rtfs,95),4) if rtfs else None,
     "errors":errors,"oom":oom,"gpu":torch.cuda.get_device_name(0)}
SUM.write_text(json.dumps(agg,indent=2)+"\n")
print("DONE", json.dumps(agg))
