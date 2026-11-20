import os, json, time, sys, asyncio, random, statistics, argparse
os.environ.setdefault('CUDA_VISIBLE_DEVICES','0')
os.environ.setdefault('ARSENAL_DEBUG','1')
os.environ.setdefault('ARSENAL_POCKET_TTS','/kaggle/working/pocket-tts')
os.environ.setdefault('ARSENAL_MODEL_DIR','/kaggle/working/arsenal/Code/model')
for k,v in [('ARSENAL_MAX_QUEUE','4096'),('ARSENAL_MAX_ROWS','640'),('ARSENAL_MAX_BATCH','640'),('ARSENAL_BATCH_TARGET','640'),('ARSENAL_CALL_FIRST_SUB_BATCH','640')]:
    os.environ[k]=v
sys.path.insert(0,'Code')
from fastapi.testclient import TestClient
from batch.server import create_app
from batch.job_classes import JobClass
from batch.call_chunker import split_call_text

TEXT="Hello, can you hear me now?"
OUT='Code/probes/out'

def save(name,data):
    path=f'{OUT}/{name}'
    with open(path,'w') as f: json.dump(data,f,indent=2)
    print('saved',name,flush=True)

def pstats(vals):
    if not vals: return {'count':0,'p50':None,'p95':None,'max':None,'min':None}
    s=sorted(vals)
    return {'count':len(s),'p50':statistics.median(s),'p95':s[min(len(s)-1,int(len(s)*0.95))],'max':max(s),'min':min(s)}

app=create_app()

async def one_call_internal(worker, eng, app_state, profile, first_frames, text, first_only=True):
    loop=asyncio.get_running_loop()
    stream=eng._stream_for(profile)
    cache=app_state.chunk_cache
    chunks = await loop.run_in_executor(None, cache.get_or_split, (text, first_frames), lambda: split_call_text(stream, text, first_frames))
    worker.enter_call()
    t0=time.monotonic()
    first_byte_ms=None
    try:
        for index, chunk in enumerate(chunks):
            if first_only and index>0: break
            cls=JobClass.CALL_FIRST if index==0 else JobClass.CALL_CONT
            got={'t':None}
            def on_chunk(frame, elapsed):
                if got['t'] is None: got['t']=time.monotonic()
            job=worker.submit([chunk], first_frames, profile, job_class=cls, mode='call', on_chunk=on_chunk)
            await asyncio.wrap_future(job.future)
            if index==0:
                first_byte_ms=(got['t']-t0)*1000.0 if got['t'] is not None else (time.monotonic()-t0)*1000.0
    finally:
        worker.exit_call()
    return {'first_byte_ms':first_byte_ms}

async def poisson_run(worker, eng, app_state, rate, duration_s=30, Q=3, H=10):
    Bcap=max(640, int(rate*3))
    os.environ['ARSENAL_MAX_BATCH']=str(Bcap); os.environ['ARSENAL_MAX_ROWS']=str(Bcap); os.environ['ARSENAL_BATCH_TARGET']=str(Bcap)
    os.environ['ARSENAL_CALL_FIRST_MAX_BATCH']=str(Bcap)
    os.environ['ARSENAL_CALL_FIRST_QUIET_MS']=str(Q)
    os.environ['ARSENAL_CALL_FIRST_HARD_CAP_MS']=str(H)
    os.environ['ARSENAL_CALL_POISSON']='1'
    os.environ['ARSENAL_BATCH_WINDOW_MS']='5'
    worker.reload_config()
    # warm
    await asyncio.gather(*[asyncio.create_task(one_call_internal(worker,eng,app_state,None,16,TEXT,True)) for _ in range(min(32,rate))], return_exceptions=True)
    await asyncio.sleep(0.2)
    q_samples=[]; stop=time.monotonic()+duration_s
    async def sampler():
        while time.monotonic()<stop:
            q_samples.append(worker.depth); await asyncio.sleep(0.1)
    samp=asyncio.create_task(sampler())
    tasks=[]; next_t=time.monotonic(); t0_wall=time.monotonic()
    bs0=list(app_state.metrics.batch_size)
    while next_t < stop:
        now=time.monotonic()
        if now < next_t: await asyncio.sleep(next_t-now)
        tasks.append(asyncio.create_task(one_call_internal(worker,eng,app_state,None,16,TEXT,True)))
        next_t += random.expovariate(rate)
    res=await asyncio.gather(*tasks, return_exceptions=True)
    await samp
    elapsed=time.monotonic()-t0_wall
    fb=[r['first_byte_ms'] for r in res if isinstance(r,dict) and r.get('first_byte_ms') is not None]
    errs=sum(1 for r in res if isinstance(r,Exception))
    bs=list(app_state.metrics.batch_size)[len(bs0):]
    batches_count=len(bs)
    return {'rate':rate,'duration':duration_s,'count':len(tasks),'Q':Q,'H':H,'first_byte':pstats(fb),
            'errors':errs,'queue_depth':pstats([float(x) for x in q_samples]),
            'batches':batches_count,'batches_per_s':batches_count/elapsed if elapsed>0 else 0,
            'batch_sizes_sample':bs[:20],'batch_sizes_stats':pstats([float(x) for x in bs])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['poisson','mixed'], default='poisson')
    ap.add_argument('--rate', type=int, default=0)
    ap.add_argument('--all-poisson', action='store_true')
    args=ap.parse_args()

    with TestClient(app) as client:
        for i in range(300):
            if client.get('/health').json().get('ready'): print('ready',flush=True); break
            time.sleep(1)
        worker=app.state.worker; eng=app.state.engine; app_state=app.state
        if args.mode=='poisson':
            rates=[64,128,224,288] if args.all_poisson or args.rate==0 else [args.rate]
            out={}
            try:
                out=json.load(open(f'{OUT}/trust_poisson_30s.json'))
            except Exception:
                out={}
            for rate in rates:
                pr=asyncio.run(poisson_run(worker,eng,app_state,rate,30,3,10))
                out[str(rate)]=pr
                save('trust_poisson_30s.json', out)
                print('POISSON', rate, pr['first_byte']['p50'], pr['first_byte']['p95'], pr['queue_depth']['p95'], pr['batches_per_s'], pr['errors'], flush=True)
        elif args.mode=='mixed':
            os.environ['ARSENAL_CALL_POISSON']='0'
            os.environ['ARSENAL_CALL_FIRST_QUIET_MS']='3'
            os.environ['ARSENAL_CALL_FIRST_HARD_CAP_MS']='40'
            os.environ['ARSENAL_BATCH_WINDOW_MS']='5'
            for k in ['ARSENAL_MAX_BATCH','ARSENAL_MAX_ROWS','ARSENAL_BATCH_TARGET','ARSENAL_CALL_FIRST_MAX_BATCH']:
                os.environ[k]='256'
            worker.reload_config()
            client.get(f'/debug/callramp?b=32&repeats=1&first_only=1&first_max_frames=16&window=5&text={TEXT.replace(" ","%20")}')
            r=client.get('/debug/callmixed?call=128&normal=32&first_max_frames=16&cont_max_frames=160&first_only=1')
            mixed=r.json(); save('trust_mixed_after_fix.json', mixed)
            print('MIXED', json.dumps(mixed), flush=True)
            # also full calls + normal? callmixed currently runs full call streams? first_only param default 1 in my earlier edit - check
            r2=client.get('/debug/callmixed?call=128&normal=32&first_max_frames=16&cont_max_frames=160&first_only=0')
            mixed2=r2.json(); save('trust_mixed_full_calls.json', mixed2)
            print('MIXED_FULL', json.dumps(mixed2), flush=True)

if __name__=='__main__':
    main()
