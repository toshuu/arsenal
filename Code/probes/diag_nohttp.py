"""No-HTTP bisect: submit B jobs to BatchWorker from threads."""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Code"))
extra = os.getenv("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts")
sys.path.insert(0, extra)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bs", default="32,37,38,48")
    ap.add_argument("--bursts", type=int, default=2)
    ap.add_argument("--window", type=int, default=150)
    ap.add_argument("--profile", default="v1")
    ap.add_argument("--out", default=str(ROOT / "probes" / "out" / "diag_nohttp.json"))
    args = ap.parse_args()
    bs = [int(x) for x in args.bs.split(",") if x]

    os.environ.setdefault("ARSENAL_MAX_BATCH", str(max(bs)))
    os.environ.setdefault("ARSENAL_MAX_ROWS", str(max(bs)))
    os.environ.setdefault("ARSENAL_BATCH_TARGET", str(max(bs)))
    os.environ["ARSENAL_BATCH_WINDOW_MS"] = str(args.window)
    os.environ.setdefault("ARSENAL_MODEL_DIR", str(ROOT / "Code" / "model"))
    os.environ.setdefault("ARSENAL_VOICE_PROFILES", f"v1={ROOT}/Code/probes/ref/voice.wav")  # placeholder

    # need built profiles
    profile_dir = Path("/tmp/arsenal_load_profiles")
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "Code" / "batch" / "build_voice_profiles.py"), str(profile_dir),
                    f"v1={ROOT}/Code/probes/ref/voice.wav"], cwd=ROOT,
                   env={**os.environ, "PYTHONPATH": extra + os.pathsep + os.environ.get("PYTHONPATH","")},
                   check=True, capture_output=True, timeout=300)
    os.environ["ARSENAL_VOICE_PROFILES"] = f"v1={profile_dir}/v1.pt"

    import torch
    from batch.server import TTSEngine, BatchWorker, Metrics, Settings

    settings = Settings(max_batch=max(bs), max_rows=max(bs), max_queue=512)
    metrics = Metrics()
    engine = TTSEngine(settings)
    engine.load()

    # instrument worker
    batch_events = []
    orig_execute = None

    worker = BatchWorker(engine, settings.max_batch, settings.max_queue, settings.max_rows, metrics)
    orig_execute = worker._execute
    def inst_execute(batch):
        t0 = time.perf_counter_ns()
        rows = sum(len(j.texts) for j in batch)
        profiles = [j.profile_id for j in batch]
        orig_execute(batch)
        t1 = time.perf_counter_ns()
        batch_events.append({"rows": rows, "jobs": len(batch), "profiles": profiles[:3], "exec_ms": (t1-t0)/1e6, "t0": t0})
    worker._execute = inst_execute

    texts = [
        "Hello there.",
        "The quick brown fox jumps over the lazy dog near the river.",
        "This is a longer sentence that has several words and needs more frames to finish.",
        "नमस्ते, यह एक परीक्षण वाक्य है। This is a mixed language test for the load probe.",
    ]
    results = {}
    for b in bs:
        worker.max_batch = b
        worker.max_rows = b
        os.environ["ARSENAL_BATCH_TARGET"] = str(b)
        for burst in range(args.bursts):
            batch_events.clear()
            jobs = [None]*b
            ready = threading.Barrier(b+1)
            first = [None]*b
            def run_one(i):
                ready.wait()
                j = worker.submit([texts[i%len(texts)]], None, profile_id=args.profile, priority=0)
                jobs[i]=j
                try:
                    j.future.result(timeout=120)
                except Exception as e:
                    jobs[i]=e
            threads = [threading.Thread(target=run_one, args=(i,), daemon=True) for i in range(b)]
            for t in threads: t.start()
            ready.wait()
            t_burst = time.perf_counter()
            for t in threads: t.join(timeout=180)
            wall = time.perf_counter() - t_burst
            q=[]
            req=[]
            errs=0
            for j in jobs:
                if not hasattr(j,'created_at'):
                    errs+=1; continue
                started=j.started_at or j.created_at
                q.append((started-j.created_at)*1000)
                if j.first_chunk_at:
                    req.append((j.first_chunk_at-j.created_at)*1000)
            def pct(v,p):
                if not v: return None
                s=sorted(v); return s[min(len(s)-1,int(len(s)*p))]
            key=f"b{b}_burst{burst}"
            results[key]={"b":b,"burst":burst,"wall_s":round(wall,3),"errors":errs,
                          "req_p50":pct(req,0.5),"req_p95":pct(req,0.95),"req_max":max(req) if req else None,
                          "q_p50":pct(q,0.5),"q_p95":pct(q,0.95),"q_max":max(q) if q else None,
                          "batches":[dict(e) for e in batch_events]}
            print(json.dumps({k:v for k,v in results[key].items() if k!='batches'}, default=str), flush=True)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(results,indent=2), encoding='utf-8')
    print(json.dumps({"out":str(out)}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
