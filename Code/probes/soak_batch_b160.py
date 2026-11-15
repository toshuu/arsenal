import json, os, sys, time, logging
from pathlib import Path
import torch
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'Code'))
sys.path.insert(0, str(REPO / 'Code' / 'probes'))
os.chdir(REPO / 'Code' / 'model')
logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts, pct, first_sound_ms

VOICE = REPO / 'Code' / 'probes' / 'ref' / 'voice.wav'
PROF = REPO / 'Code' / 'probes' / 'out' / 'soak_voice.pt'
OUT = REPO / 'Code' / 'probes' / 'out' / 'soak_b160.jsonl'
OUT.parent.mkdir(parents=True, exist_ok=True)

B = 160
DURATION_S = 30 * 60
model = TTSModel.load_model(config='config.yaml').to('cuda').eval()
enable_fp16_backbone(model); model.temp = 0.3
sr = model.config.mimi.sample_rate
spf = int(round(sr / model.mimi.frame_rate))
texts = make_texts(160)
base = BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16)
base.save_voice_profile(PROF, conditioned=True)
stream = BatchedStream(model, voice_profile=PROF, max_first_tokens=16, decode_group=1, compact=True)
stream.stream(texts[:4], max_frames=4); torch.cuda.synchronize()

start = time.perf_counter()
burst = 0
summary = {"B": B, "bursts": 0, "requests": 0, "under350": 0, "errors": 0, "oom": 0,
           "p95s": [], "rtfs": [], "walls": [], "audio_s": 0.0}
with open(OUT, 'w') as f:
    while time.perf_counter() - start < DURATION_S:
        bt = [texts[(burst * 13 + r) % len(texts)] for r in range(B)]
        ft = [[] for _ in range(B)]
        t0 = time.perf_counter()
        def cb(r, c, e, ft=ft, t0=t0): ft[r].append(time.perf_counter() - t0)
        try:
            audio = stream.stream(bt, on_chunk=cb)
            torch.cuda.synchronize()
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            summary["oom"] += 1; summary["errors"] += 1
            rec = {"burst": burst, "error": "oom"}
            f.write(json.dumps(rec) + "\n"); f.flush()
            burst += 1
            continue
        except Exception as e:
            summary["errors"] += 1
            rec = {"burst": burst, "error": str(e)}
            f.write(json.dumps(rec) + "\n"); f.flush()
            burst += 1
            continue
        wall = time.perf_counter() - t0
        ms = [first_sound_ms(audio[r], ft[r], spf) for r in range(B)]
        ms = [x for x in ms if x is not None]
        audio_s = sum(a.numel() for a in audio) / sr
        rtf = wall / audio_s if audio_s else None
        p50 = pct(ms, 50) if ms else None
        p95 = pct(ms, 95) if ms else None
        under = sum(1 for x in ms if x <= 350)
        summary["bursts"] += 1
        summary["requests"] += len(ms)
        summary["under350"] += under
        summary["p95s"].append(p95)
        summary["rtfs"].append(rtf)
        summary["walls"].append(wall)
        summary["audio_s"] += audio_s
        rec = {"burst": burst, "wall": round(wall,3), "audio_s": round(audio_s,3),
               "rtf": round(rtf,4) if rtf else None, "p50": round(p50,1) if p50 else None,
               "p95": round(p95,1) if p95 else None, "under": under, "n": len(ms)}
        f.write(json.dumps(rec) + "\n"); f.flush()
        if burst % 20 == 0:
            print(f"burst={burst} p95={rec['p95']} under={under}/{len(ms)} rtf={rec['rtf']} elapsed={time.perf_counter()-start:.0f}s", flush=True)
        burst += 1

elapsed = time.perf_counter() - start
agg = {
    "B": B, "duration_s": round(elapsed,1), "bursts": summary["bursts"],
    "requests": summary["requests"], "under350": summary["under350"],
    "under350_pct": round(100*summary["under350"]/summary["requests"],3) if summary["requests"] else None,
    "p95_median": round(pct(summary["p95s"],50),2) if summary["p95s"] else None,
    "p95_p95": round(pct(summary["p95s"],95),2) if summary["p95s"] else None,
    "p95_max": round(max(summary["p95s"]),2) if summary["p95s"] else None,
    "rtf_median": round(pct(summary["rtfs"],50),4) if summary["rtfs"] else None,
    "rtf_p95": round(pct(summary["rtfs"],95),4) if summary["rtfs"] else None,
    "rtf_max": round(max(summary["rtfs"]),4) if summary["rtfs"] else None,
    "errors": summary["errors"], "oom": summary["oom"], "gpu": torch.cuda.get_device_name(0),
}
(Path(REPO/'Code/probes/out/soak_b160_summary.json')).write_text(json.dumps(agg, indent=2) + '\n')
print('DONE', json.dumps(agg))
