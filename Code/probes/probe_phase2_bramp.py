"""Phase 2 B-ramp: sentence vs utterance, server callramp."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Code/probes/out/phase2_bramp"
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
PORT = int(os.getenv("ARSENAL_BRAMP_PORT", "8120"))
TEXT = "Hello, this is Arsenal. Can you hear me clearly right now?"

def wait(base, timeout=300):
    d=time.time()+timeout
    while time.time()<d:
        try:
            r=requests.get(base+"/health",timeout=2)
            if r.ok and r.json().get("ready"): return
        except Exception: pass
        time.sleep(1)
    raise RuntimeError("server not ready")

def run_case(base, mode, b, reps=3):
    rows=[]
    for rep in range(reps):
        r=requests.get(base+"/debug/callramp", params={"b":b,"repeats":1,"first_only":1,"stream_mode":mode,"text":TEXT}, timeout=600)
        r.raise_for_status()
        d=r.json(); run=d["runs"][0]
        fb=run.get("first_byte_ms",{})
        rows.append({"mode":mode,"b":b,"rep":rep,"p50":fb.get("p50"),"p95":fb.get("p95"),"max":fb.get("max"),"errors":run.get("errors"),"batch_sizes":run.get("batch_sizes"),"vram_after":run.get("vram_mb",{}).get("after")})
        print(json.dumps(rows[-1]), flush=True)
    p95s=[r["p95"] for r in rows if isinstance(r.get("p95"),(int,float))]
    return {"mode":mode,"b":b,"reps":reps,"p95_median":round(sorted(p95s)[len(p95s)//2],2) if p95s else None,"rows":rows}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sentence","utterance","both"], default="both")
    ap.add_argument("--out", type=Path, default=OUT/"ramp.json")
    args=ap.parse_args()
    args.out = args.out if args.out.is_absolute() else (ROOT/args.out).resolve()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    modes=["sentence","utterance"] if args.mode=="both" else [args.mode]
    bs=[32,64,96,128,224,320,448]
    env=os.environ.copy(); env.update({"ARSENAL_PREWARM":"0","ARSENAL_MODEL_DIR":str(ROOT/"Code/model"),"ARSENAL_VOICE":str(REF),"ARSENAL_DEBUG":"1"})
    log=(args.out.parent/"server.log").open("w")
    p=subprocess.Popen([sys.executable,"-m","uvicorn","batch.server:app","--host","127.0.0.1","--port",str(PORT)],cwd=str(ROOT/"Code"),env=env,stdout=log,stderr=subprocess.STDOUT)
    try:
        wait(f"http://127.0.0.1:{PORT}")
        results=[]
        for mode in modes:
            for b in bs:
                results.append(run_case(f"http://127.0.0.1:{PORT}", mode, b, reps=3))
        out={"ok":True,"modes":modes,"bs":bs,"rows":results}
        args.out.write_text(json.dumps(out,indent=2))
        print(json.dumps({"ok":True,"out":str(args.out),"rows":len(results)}))
    finally:
        p.terminate()
        try: p.wait(timeout=20)
        except Exception: p.kill()
        log.close()

if __name__=="__main__":
    main()
