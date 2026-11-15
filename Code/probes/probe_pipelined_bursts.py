"""Pipelined burst probe (CPU prep overlap)."""

import argparse, json, logging, os, sys, time
from concurrent.futures import ThreadPoolExecutor
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

def prep(texts, b, rnd):
    return [texts[(rnd * 13 + r) % len(texts)] for r in range(b)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--b", type=int, default=128)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--voice", default=str(REPO / "Code/probes/ref/voice.wav"))
    ap.add_argument("--profile", default=str(REPO / "Code/probes/out/voice_4s_cond.pt"))
    ap.add_argument("--out", default=str(REPO / "Code/probes/out/probe_pipelined.json"))
    args = ap.parse_args()
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
    all_ms=[]; walls=[]; bursts=[]
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(prep, texts, args.b, 0)
        for rnd in range(args.rounds):
            bt = fut.result()
            if rnd + 1 < args.rounds:
                fut = ex.submit(prep, texts, args.b, rnd + 1)
            ft=[[] for _ in range(args.b)]
            t0=time.perf_counter()
            def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
            audio=stream.stream(bt,on_chunk=cb); torch.cuda.synchronize()
            wall=time.perf_counter()-t0; walls.append(wall)
            bms=[first_sound_ms(audio[r],ft[r],spf) for r in range(args.b)]
            bms=[x for x in bms if x is not None]
            bursts.append({"p95": round(pct(bms,95),2), "under": sum(1 for x in bms if x<=350), "n": len(bms)})
            all_ms.extend(bms)
    agg={"B":args.b,"rounds":args.rounds,"p50":round(pct(all_ms,50),2),"p95":round(pct(all_ms,95),2),
         "under":sum(1 for x in all_ms if x<=350),"total":len(all_ms),
         "under_pct":round(100*sum(1 for x in all_ms if x<=350)/len(all_ms),3),"bursts":bursts}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(agg, indent=2)+"\n")
    print(json.dumps(agg))
    print("PIPELINED_DONE")
if __name__ == "__main__":
    main()
