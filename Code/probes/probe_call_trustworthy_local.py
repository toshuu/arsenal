import os, json, time, sys, asyncio, random, math, statistics
os.environ.setdefault('CUDA_VISIBLE_DEVICES','0')
os.environ.setdefault('ARSENAL_DEBUG','1')
os.environ.setdefault('ARSENAL_POCKET_TTS','/kaggle/working/pocket-tts')
os.environ.setdefault('ARSENAL_MODEL_DIR','/kaggle/working/arsenal/Code/model')
os.environ.setdefault('ARSENAL_MAX_QUEUE','4096')
os.environ.setdefault('ARSENAL_MAX_ROWS','640')
os.environ.setdefault('ARSENAL_MAX_BATCH','640')
os.environ.setdefault('ARSENAL_BATCH_TARGET','640')
os.environ.setdefault('ARSENAL_CALL_FIRST_SUB_BATCH','640')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from batch.server import create_app
from batch.job_classes import JobClass

TEXT="Hello, can you hear me now?"
OUT_DIR=os.path.join(os.path.dirname(__file__),'out')
os.makedirs(OUT_DIR, exist_ok=True)

def save(name,data):
    path=os.path.join(OUT_DIR,name)
    with open(path,'w') as f: json.dump(data,f,indent=2)
    print('saved',path,flush=True)

def pstats(vals):
    if not vals: return {'p50':None,'p95':None,'count':0,'max':None,'min':None}
    s=sorted(vals)
    return {'count':len(s),'p50':statistics.median(s),'p95':s[min(len(s)-1,int(len(s)*0.95))],'max':max(s),'min':min(s)}

def snap_metrics(m):
    s=m.snapshot()
    return {
        'batch_size_n': s['batch_size']['count'],
        'batch_wall_n': s['batch_wall_ms']['count'],
        'batch_size_vals': list(m.batch_size),
        'batch_wall_vals': list(m.batch_wall_ms),
        'queue_ms': s['queue_ms'],
    }

app=create_app()

with TestClient(app) as client:
    for i in range(300):
        if client.get('/health').json().get('ready'):
            print('ready',flush=True); break
        time.sleep(1)
    else:
        raise SystemExit('not ready')

    worker=app.state.worker
    metrics=app.state.metrics
    eng=app.state.engine

    def set_env(B, sub=None, w=5, mf=16):
        os.environ['ARSENAL_MAX_BATCH']=str(B)
        os.environ['ARSENAL_MAX_ROWS']=str(B)
        os.environ['ARSENAL_BATCH_TARGET']=str(B)
        os.environ['ARSENAL_BATCH_WINDOW_MS']=str(w)
        os.environ['ARSENAL_CALL_FIRST_SUB_BATCH']=str(sub if sub is not None else B)
        worker.reload_config()

    def callramp(B, repeats=1, first_only=1, mf=16, w=5, text=TEXT, cont=160):
        set_env(B, sub=B, w=w, mf=mf)
        url=f'/debug/callramp?b={B}&repeats={repeats}&first_only={first_only}&first_max_frames={mf}&window={w}&cont_max_frames={cont}&text={text.replace(" ","%20")}'
        r=client.get(url)
        return r.json()

    report_rows=[]

    # Step 2 & 3 & 4 helpers: run cell with cold + 2 warmup + warm measured, capture batch metrics
    def run_cell(B, first_only=1, mf=16, w=5, text=TEXT, label=''):
        set_env(B, sub=B, w=w, mf=mf)
        # clear metric lists relevant? keep global but track deltas
        def delta(before, after_key, vals_key):
            bcount=before[after_key]
            vals=metrics.snapshot() # not direct; easier use lists
            return None
        # cold = first burst
        bs0=list(metrics.batch_size); bw0=list(metrics.batch_wall_ms)
        cold=callramp(B,1,first_only,mf,w,text)
        cold_bs=list(metrics.batch_size)[len(bs0):]
        cold_bw=list(metrics.batch_wall_ms)[len(bw0):]
        # 2 warmups
        callramp(B,1,first_only,mf,w,text)
        callramp(B,1,first_only,mf,w,text)
        # warm measured
        bs1=list(metrics.batch_size); bw1=list(metrics.batch_wall_ms)
        warm=callramp(B,1,first_only,mf,w,text)
        warm_bs=list(metrics.batch_size)[len(bs1):]
        warm_bw=list(metrics.batch_wall_ms)[len(bw1):]
        return {'B':B,'first_only':first_only,'mf':mf,'w':w,'label':label,
                'cold':cold,'cold_batch_sizes':cold_bs,'cold_batch_wall_ms':cold_bw,
                'warm':warm,'warm_batch_sizes':warm_bs,'warm_batch_wall_ms':warm_bw}

    # Step 2: explain a_first_only vs b_full at B=224
    print('STEP2',flush=True)
    set_env(224,224,5,16)
    # warm engine/app state a bit
    callramp(8,1,1,16,5,TEXT); callramp(8,1,1,16,5,TEXT)
    # first-only
    a_res=[]
    # 2 warmups at 224
    callramp(224,1,1,16,5,TEXT); callramp(224,1,1,16,5,TEXT)
    bs0=list(metrics.batch_size); bw0=list(metrics.batch_wall_ms)
    a=callramp(224,1,1,16,5,TEXT)
    a_bs=list(metrics.batch_size)[len(bs0):]; a_bw=list(metrics.batch_wall_ms)[len(bw0):]
    # full (same text => single chunk? check)
    callramp(224,1,0,16,5,TEXT); callramp(224,1,0,16,5,TEXT)
    bs0=list(metrics.batch_size); bw0=list(metrics.batch_wall_ms)
    bfull=callramp(224,1,0,16,5,TEXT)
    b_bs=list(metrics.batch_size)[len(bs0):]; b_bw=list(metrics.batch_wall_ms)[len(bw0):]
    # full with multi-chunk text
    MCT="Hello, this is a call from Arsenal. The quick brown fox jumps."
    callramp(224,1,0,16,5,MCT); callramp(224,1,0,16,5,MCT)
    bs0=list(metrics.batch_size); bw0=list(metrics.batch_wall_ms)
    bmc=callramp(224,1,0,16,5,MCT)
    bmc_bs=list(metrics.batch_size)[len(bs0):]; bmc_bw=list(metrics.batch_wall_ms)[len(bw0):]
    step2={'first_only_singlechunk':{'run':a,'batch_sizes':a_bs,'batch_wall_ms':a_bw},
           'full_singlechunk':{'run':bfull,'batch_sizes':b_bs,'batch_wall_ms':b_bw},
           'full_multichunk':{'run':bmc,'batch_sizes':bmc_bs,'batch_wall_ms':bmc_bw,'text':MCT}}
    save('trust_step2_compare.json', step2)
    print('STEP2 done', flush=True)

    # Step 1 & 3 & 4: repeatability and cliff with fixed warmup/cold
    print('STEP1,3,4',flush=True)
    repeat_results={}
    for B in [128,224,288,384]:
        set_env(B,B,5,16)
        # cold (first burst at this B after possible prior different B - counts as cold-for-cell)
        cold=callramp(B,1,1,16,5,TEXT)
        # 2 discarded warmups
        callramp(B,1,1,16,5,TEXT); callramp(B,1,1,16,5,TEXT)
        reps=[]
        per_batch=[]
        for i in range(10):
            bs0=list(metrics.batch_size); bw0=list(metrics.batch_wall_ms)
            r=callramp(B,1,1,16,5,TEXT)
            run=r['runs'][0]
            reps.append({'i':i,'p50':run['first_byte_ms']['p50'],'p95':run['first_byte_ms']['p95'],
                         'errors':run['errors'],'t_submit_p50':run.get('timing_submit_ms',{}).get('p50'),
                         't_batch_start_p50':run.get('timing_batch_start_ms',{}).get('p50'),
                         't_first_emit_p50':run.get('timing_first_emit_ms',{}).get('p50')})
            per_batch.append({'batch_sizes':list(metrics.batch_size)[len(bs0):],'batch_wall_ms':list(metrics.batch_wall_ms)[len(bw0):]})
        p95s=[x['p95'] for x in reps]
        p50s=[x['p50'] for x in reps]
        spread={'p95_min':min(p95s),'p95_max':max(p95s),'p95_range':max(p95s)-min(p95s),
                'p50_min':min(p50s),'p50_max':max(p50s),'p50_range':max(p50s)-min(p50s)}
        entry={'B':B,'cold':{'p50':cold['runs'][0]['first_byte_ms']['p50'],'p95':cold['runs'][0]['first_byte_ms']['p95'],'errors':cold['runs'][0]['errors']},
               'repeats':reps,'spread':spread,'per_batch':per_batch}
        repeat_results[str(B)]=entry
        report_rows.append({'test':'repeat_first_only','B':B,'arrival':'burst','warm':'cold','first_p50':entry['cold']['p50'],'first_p95':entry['cold']['p95'],'spread':'-','errors':entry['cold']['errors']})
        report_rows.append({'test':'repeat_first_only','B':B,'arrival':'burst','warm':'warm(10)','first_p50':statistics.median(p50s),'first_p95':statistics.median(p95s),'spread':spread['p95_range'],'errors':sum(x['errors'] for x in reps)})
        print('REP',B,'cold',entry['cold']['p95'],'warm_p95_med',statistics.median(p95s),'spread',spread['p95_range'],flush=True)
    save('trust_step134_repeat.json', repeat_results)

    # Step 5: Poisson arrivals
    print('STEP5 poisson',flush=True)
    async def one_call_internal(profile, first_frames, cont_frames, text):
        loop=asyncio.get_running_loop()
        stream=eng._stream_for(profile)
        cache=app.state.chunk_cache
        from batch.call_chunker import split_call_text
        chunks = await loop.run_in_executor(None, cache.get_or_split, (text, first_frames), lambda: split_call_text(stream, text, first_frames))
        worker.enter_call()
        t0=time.monotonic()
        first_byte_ms=None
        try:
            for index, chunk in enumerate(chunks[:1]): # first only
                cls=JobClass.CALL_FIRST
                got={'t':None}
                def on_chunk(frame, elapsed):
                    if got['t'] is None: got['t']=time.monotonic()
                job=worker.submit([chunk], first_frames, profile, job_class=cls, mode='call', on_chunk=on_chunk)
                await asyncio.wrap_future(job.future)
                if got['t'] is not None: first_byte_ms=(got['t']-t0)*1000.0
                else: first_byte_ms=(time.monotonic()-t0)*1000.0
        except Exception as e:
            return {'error':str(e)}
        finally:
            worker.exit_call()
        return {'first_byte_ms':first_byte_ms}

    async def poisson_run(rate, duration_s=60, Bcap=640):
        set_env(min(640, max(224, int(rate*2))), min(640,max(224,int(rate*2))), 5, 16)
        # warmup
        tasks=[asyncio.create_task(one_call_internal(None,16,160,TEXT)) for _ in range(min(32,int(rate)))]
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0.2)
        results=[]
        q_samples=[]
        stop=time.monotonic()+duration_s
        async def sampler():
            while time.monotonic()<stop:
                q_samples.append(worker.depth)
                await asyncio.sleep(0.1)
        samp=asyncio.create_task(sampler())
        tasks=[]
        next_t=time.monotonic()
        while next_t < stop:
            now=time.monotonic()
            if now < next_t:
                await asyncio.sleep(next_t-now)
            tasks.append(asyncio.create_task(one_call_internal(None,16,160,TEXT)))
            next_t += random.expovariate(rate)
        res=await asyncio.gather(*tasks, return_exceptions=True)
        await samp
        for r in res:
            if isinstance(r,dict) and 'first_byte_ms' in r and r['first_byte_ms'] is not None:
                results.append(r['first_byte_ms'])
            elif isinstance(r,Exception):
                results.append(None)
        errs=sum(1 for r in res if isinstance(r,Exception) or (isinstance(r,dict) and 'error' in r))
        fb=[x for x in results if isinstance(x,(int,float))]
        return {'rate':rate,'duration':duration_s,'count':len(tasks),'first_byte':pstats(fb),'errors':errs,
                'queue_depth':pstats([float(x) for x in q_samples])}

    poisson={}
    for rate in [64,128,224,288]:
        # shorter if needed? 60s required
        try:
            pr=asyncio.run(poisson_run(rate,60))
        except Exception as e:
            pr={'rate':rate,'error':str(e)}
        poisson[str(rate)]=pr
        print('POISSON',rate, pr.get('first_byte'), pr.get('queue_depth'), pr.get('errors'), flush=True)
        if 'first_byte' in pr:
            report_rows.append({'test':'poisson_first_only','B':rate,'arrival':f'poisson~{rate}/s','warm':'warm','first_p50':pr['first_byte']['p50'],'first_p95':pr['first_byte']['p95'],'spread':'-','errors':pr.get('errors',0)})
    save('trust_step5_poisson.json', poisson)

    # Step 6: Mixed fix
    print('STEP6 mixed',flush=True)
    set_env(256,256,5,16)
    # warmup
    callramp(32,1,1,16,5,TEXT)
    # mixed 128 call first-only + 32 normal
    r=client.get('/debug/callmixed?call=128&normal=32&first_max_frames=16&cont_max_frames=160&first_only=1')
    mixed=r.json()
    save('trust_step6_mixed.json', mixed)
    report_rows.append({'test':'mixed_call128_norm32','B':128,'arrival':'burst','warm':'warm','first_p50':mixed.get('call_first_byte_ms',{}).get('p50'),'first_p95':mixed.get('call_first_byte_ms',{}).get('p95'),'spread':'-','errors':mixed.get('errors')})
    print('MIXED', json.dumps(mixed), flush=True)

    # summary table
    save('trust_report_rows.json', report_rows)
    print('\nREPORT',flush=True)
    print('test|B|arrival|warm/cold|first-byte p50/p95|spread|errors')
    for r in report_rows:
        print(f"{r['test']}|{r['B']}|{r['arrival']}|{r['warm']}|{r['first_p50']}/{r['first_p95']}|{r['spread']}|{r['errors']}")

print('DONE',flush=True)
