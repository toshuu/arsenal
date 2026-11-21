"""Arsenal TTS Modal app: one T4, one bounded batch worker.

Deploy the serving app:
    modal deploy Code/deploy/modal_app.py

Build the voice cache and profiles once (dev app):
    modal run Code/deploy/modal_app.py::build_assets

Run helpers (dev app, does not stop the serving app):
    modal run Code/deploy/modal_app.py::probe
    modal run Code/deploy/modal_app.py::direct_bench --bs 32

Stop the serving app and the GPU when idle:
    modal app stop arsenal-tts-t4
"""

from __future__ import annotations

import modal

APP_NAME = "arsenal-tts-t4"
DEV_NAME = "arsenal-tts-dev"
CODE_DIR = "/root/arsenal/Code"
CACHE_DIR = "/cache"
PROFILES = f"{CACHE_DIR}/profiles"
VOICE_CACHE = f"{CACHE_DIR}/voice_cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1")
    .pip_install(
        "pocket-tts==4.0.1",
        "fastapi>=0.100",
        "uvicorn[standard]>=0.13",
        "httpx",
        "websockets",
    )
    .add_local_dir("Code/batch", remote_path=f"{CODE_DIR}/batch")
    .add_local_dir("Code/model", remote_path=f"{CODE_DIR}/model")
    .add_local_dir("Code/probes/ref", remote_path=f"{CODE_DIR}/probes/ref")
    .add_local_dir("Code/probes", remote_path=f"{CODE_DIR}/probes")
)

cache = modal.Volume.from_name("arsenal-tts-cache", create_if_missing=True)

app = modal.App(APP_NAME)
dev = modal.App(DEV_NAME)

common_env = {
    "PYTHONUNBUFFERED": "1",
    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
    "ARSENAL_MODEL_DIR": f"{CODE_DIR}/model",
    "ARSENAL_VOICE_CACHE": VOICE_CACHE,
    "ARSENAL_VOICE_PROFILES": f"v1={PROFILES}/v1.pt;v2={PROFILES}/v2.pt",
    "ARSENAL_MAX_BATCH": "640",
    "ARSENAL_MAX_ROWS": "640",
    "ARSENAL_MAX_QUEUE": "4096",
    "ARSENAL_MAX_FRAMES": "192",
    "ARSENAL_BATCH_WINDOW_MS": "150",
    "ARSENAL_BATCH_TARGET": "640",
    "ARSENAL_CALL_FIRST_QUIET_MS": "3",
    "ARSENAL_CALL_FIRST_HARD_CAP_MS": "40",
    "ARSENAL_CALL_FIRST_GRACE_MS": "10",
    "ARSENAL_CALL_FIRST_MAX_BATCH": "640",
    "ARSENAL_CALL_FIRST_MAX_FRAMES": "8",
    "ARSENAL_PREWARM": "1",
    "ARSENAL_PREWARM_B": "192",
    "ARSENAL_TIMELINE": "1",
    "ARSENAL_DEBUG": "1",
}


@dev.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    timeout=1200,
)
def build_assets() -> str:
    """Build voice cache and profiles into the persistent Volume. Idempotent."""
    import os
    import subprocess

    os.chdir("/root/arsenal")
    os.makedirs(PROFILES, exist_ok=True)
    os.makedirs(VOICE_CACHE, exist_ok=True)
    out: list[str] = []

    if not os.path.exists(f"{PROFILES}/v1.pt"):
        subprocess.run(
            [
                "python",
                "Code/batch/build_voice_profiles.py",
                PROFILES,
                "v1=Code/probes/ref/voice.wav",
                "v2=Code/probes/ref/voice.wav",
            ],
            cwd="/root/arsenal",
            check=True,
        )
        out.append("profiles built")
    else:
        out.append("profiles present")

    if not os.path.exists(f"{VOICE_CACHE}/d4084099c4e63fd8.pt"):
        env = dict(os.environ)
        env["ARSENAL_VOICE_CACHE"] = VOICE_CACHE
        subprocess.run(
            ["python", "Code/batch/build_voice_cache.py"],
            cwd="/root/arsenal",
            env=env,
            check=True,
        )
        out.append("voice cache built")
    else:
        out.append("voice cache present")

    cache.commit()
    return "; ".join(out)


@dev.function(image=image, timeout=1800, cpu=4, memory=8192)
def probe(
    bursts: int = 2,
    per_burst: int = 224,
    single_profile: str = "v1",
    limits: int = 256,
    out: str = "/tmp/probe.json",
) -> int:
    """Co-located load prober. Runs in the same Modal region as serve."""
    import os
    import subprocess

    e = dict(os.environ)
    e.update(
        {
            "ARSENAL_LOAD_BASE": "https://tushar-ps2--arsenal-tts-t4-serve.us-east.modal.run",
            "ARSENAL_LOAD_BURSTS": str(bursts),
            "ARSENAL_LOAD_PER_BURST": str(per_burst),
            "ARSENAL_LOAD_LIMITS": str(limits),
            "ARSENAL_LOAD_OUT": out,
        }
    )
    if single_profile == "none":
        e.pop("ARSENAL_LOAD_SINGLE_PROFILE", None)
        e["ARSENAL_LOAD_PROFILES"] = "0"
    else:
        e["ARSENAL_LOAD_SINGLE_PROFILE"] = single_profile
    result = subprocess.run(
        ["python", "Code/probes/probe_http_load.py"], cwd="/root/arsenal", env=e
    )
    if os.path.exists(out):
        print(open(out).read())
    return result.returncode


@dev.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    timeout=1800,
)
def direct_bench(bs: int = 32, bursts: int = 3) -> dict:
    """Direct BatchedStream first-emit test on a Modal T4, no HTTP."""
    import sys
    import time

    import torch

    sys.path.insert(0, CODE_DIR)
    from batch.server import Settings, TTSEngine

    texts = [
        "Hello there.",
        "The quick brown fox jumps over the lazy dog near the river.",
        "This is a longer sentence that has several words and needs more frames to finish.",
        "Namaste, this is a test sentence for the direct bench.",
    ] * ((bs // 4) + 1)
    texts = texts[:bs]

    engine = TTSEngine(Settings())
    engine.load()
    out: dict[str, float] = {}
    for burst in range(bursts):
        first: dict[int, float] = {}

        def cb(row: int, frame, elapsed: float) -> None:
            first.setdefault(int(row), elapsed * 1000.0)

        start = time.perf_counter()
        engine.stream.stream(texts, on_chunk=cb)
        wall = (time.perf_counter() - start) * 1000.0
        vals = sorted(first.values())
        out[f"burst_{burst}_p50_ms"] = round(vals[len(vals) // 2], 2)
        out[f"burst_{burst}_p95_ms"] = round(vals[min(len(vals) - 1, int(len(vals) * 0.95))], 2)
        out[f"burst_{burst}_max_ms"] = round(vals[-1], 2)
        out[f"burst_{burst}_wall_ms"] = round(wall, 2)
        out[f"burst_{burst}_rows"] = len(vals)
    torch.cuda.synchronize()
    print(out)
    return out


@app.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    cpu=8,
    memory=16384,
    timeout=3600,
    scaledown_window=60,
    min_containers=0,
    max_containers=1,
)
@modal.concurrent(max_inputs=256)
@modal.asgi_app()
def serve():
    import sys

    sys.path.insert(0, CODE_DIR)
    from batch.server import create_app

    return create_app()


@dev.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    cpu=8,
    memory=16384,
    timeout=7200,
)
def call_probe() -> dict:
    """Run call-mode burst+poisson on Modal T4 with current code."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    sys.path.insert(0, CODE_DIR)
    os.chdir("/root/arsenal")
    # one server, many cases
    script = r"""
import os,sys,json,time,subprocess,signal,urllib.request
ROOT='/root/arsenal'; base='http://127.0.0.1:8081'
TEXT='Hey Sam, traffic is heavy near Market Street, please wait by the gate.'
def wait_ready(timeout=300):
    d=time.monotonic()+timeout
    while time.monotonic()<d:
        try:
            with urllib.request.urlopen(base+'/health',timeout=5) as r:
                if json.loads(r.read()).get('ready'): return True
        except: pass
        time.sleep(0.5)
    raise RuntimeError('not ready')
def getj(url,timeout=30):
    with urllib.request.urlopen(url,timeout=timeout) as r: return json.loads(r.read())
def drain():
    try: getj(base+'/debug/drain?timeout=60',90)
    except Exception as e: print('drain',e,flush=True)
    for _ in range(60):
        try:
            m=getj(base+'/metrics',10); q=m.get('queue_depth',{}); a=int(m.get('active_call_sessions',0))
            qn=sum(int(q.get(k,0)) for k in ['call_first','call_cont','normal']) if isinstance(q,dict) else 0
            if qn==0 and a==0: return True
        except: pass
        time.sleep(0.5)
    return False
def run(cmd,out,timeout_s=180):
    try:
        subprocess.run(cmd,cwd=ROOT,check=False,capture_output=True,text=True,timeout=timeout_s)
        return json.load(open(out)) if os.path.exists(out) else {'error':'no_out'}
    except subprocess.TimeoutExpired:
        return {'error':'timeout'}
    except Exception as e:
        return {'error':str(e)}
env=os.environ.copy(); env.update({
 'CUDA_VISIBLE_DEVICES':'0','PYTHONUNBUFFERED':'1','ARSENAL_DEBUG':'1','ARSENAL_TIMELINE':'1',
 'PYTORCH_CUDA_ALLOC_CONF':'expandable_segments:True',
 'ARSENAL_MAX_QUEUE':'4096','ARSENAL_MAX_ROWS':'640','ARSENAL_MAX_BATCH':'640','ARSENAL_MAX_FRAMES':'192',
 'ARSENAL_BATCH_WINDOW_MS':'150','ARSENAL_BATCH_TARGET':'640',
 'ARSENAL_CALL_FIRST_QUIET_MS':'50','ARSENAL_CALL_FIRST_HARD_CAP_MS':'300','ARSENAL_CALL_FIRST_GRACE_MS':'20',
 'ARSENAL_CALL_FIRST_MAX_BATCH':'640','ARSENAL_CALL_FIRST_BUCKETS':'1',
 'ARSENAL_PREWARM':'1','ARSENAL_PREWARM_B':'192','ARSENAL_CALL_PAUSE_MAX_MS':'250'})
log=open('/tmp/fm.log','w')
srv=subprocess.Popen(['taskset','-c','0-3',sys.executable,'-m','uvicorn','batch.server:app','--app-dir','Code','--host','127.0.0.1','--port','8081','--log-level','warning','--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
results={'burst':[],'poisson':[],'compress_ms_per_1p5s':9.7}
try:
    wait_ready(); print('READY',flush=True)
    for b in [64,128,192,256]:
        drain(); time.sleep(1)
        out=f'/tmp/burst_{b}.json'
        d=run(['taskset','-c','4-7',sys.executable,'Code/probes/call_load_client.py','--url',base,'--mode','burst','--b',str(b),'--repeats','3','--warmups','2','--max-frames','96','--profile','v1','--text',TEXT,'--out',out],out,300)
        m=getj(base+'/metrics'); bs=m.get('metrics',{}).get('batch_size',{}); bw=m.get('metrics',{}).get('batch_wall_ms',{}).get('p95')
        row={'case':f'burst_b{b}','p50':d.get('p50_of_p50'),'p95':d.get('p95_of_p95'),'median_p95':d.get('median_p95'),'errors':d.get('errors'),'batches_per_rep':(bs.get('count',0)/5 if bs.get('count') else None),'batch_wall_p95':bw}
        if 'error' in d: row['err']=d['error']
        results['burst'].append(row); print(json.dumps(row),flush=True)
    for rate in [64,128,192]:
        drain(); time.sleep(1)
        out=f'/tmp/pois_{rate}.json'
        d=run(['taskset','-c','4-7',sys.executable,'Code/probes/pc_poisson.py','--url',base,'--sessions',str(max(rate,64)),'--rate',str(rate),'--duration','20','--mf','96','--profile','v1','--out',out,'--text',TEXT],out,300)
        fb=d.get('first_byte',{})
        row={'case':f'poisson_{rate}','p50':fb.get('p50'),'p95':fb.get('p95'),'errors':d.get('errors'),'completed':d.get('completed')}
        if 'error' in d: row['err']=d['error']
        results['poisson'].append(row); print(json.dumps(row),flush=True)
    json.dump(results,open('/tmp/fm_results.json','w'),indent=2)
    print('DONE',flush=True)
finally:
    srv.send_signal(signal.SIGTERM)
    try: srv.wait(timeout=20)
    except: srv.kill()
    log.close()
"""
    Path('/tmp/run_modal.py').write_text(script)
    # ensure pc_poisson in image
    r = subprocess.run([sys.executable,'/tmp/run_modal.py'], text=True, timeout=3600)
    print('RC',r.returncode)
    p=Path('/tmp/fm_results.json')
    return json.loads(p.read_text()) if p.exists() else {'error':'no_results','stdout':r.stdout[-2000:],'stderr':r.stderr[-2000:]}
