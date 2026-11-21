import argparse, asyncio, json, random, time, statistics
import websockets

def pstats(v):
    if not v: return {'p50':None,'p95':None,'count':0}
    s=sorted(v); return {'p50':statistics.median(s),'p95':s[min(len(s)-1,int(len(s)*0.95))],'count':len(s),'max':max(s)}

async def worker(ws, url, profile, text, mf, timeout, first_only=True):
    # ws already started
    t_send=time.perf_counter()
    try:
        await ws.send(json.dumps({"type":"text","text":text,"max_frames":mf,"first_only":first_only,"sent_ns":time.time_ns()}))
        t_first=None
        while True:
            msg=await asyncio.wait_for(ws.recv(), timeout)
            if isinstance(msg,(bytes,bytearray)):
                if t_first is None: t_first=time.perf_counter()
                if first_only:
                    try: await ws.send(json.dumps({"type":"cancel"}))
                    except: pass
                    # drain events until error/cancelled/chunk_done? server sends chunk_done then breaks, but we cancelled; easier break
                    break
                continue
            ev=json.loads(msg)
            if ev.get('event') in ('chunk_done','error','cancelled','flushed'): break
        if t_first is None: return {'error':'no_audio'}
        return {'ms':(t_first-t_send)*1000}
    except Exception as e:
        return {'error':str(e)}

async def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--url',default='http://127.0.0.1:8081')
    ap.add_argument('--sessions',type=int,default=320)
    ap.add_argument('--rate',type=int,default=256)
    ap.add_argument('--duration',type=int,default=30)
    ap.add_argument('--text',default='Hello, can you hear me now?')
    ap.add_argument('--mf',type=int,default=8)
    ap.add_argument('--profile',default='v1')
    ap.add_argument('--out',required=True)
    ap.add_argument('--timeout',type=float,default=30)
    args=ap.parse_args()
    base=args.url.rstrip('/')
    wsurl=('ws://'+base[len('http://'):] if base.startswith('http://') else 'wss://'+base[len('https://'):])+'/ws/tts'
    conns=[]
    conn_ms=[]; start_ms=[]
    async def open_one():
        t0=time.perf_counter()
        ws=await websockets.connect(wsurl,max_size=2**24,open_timeout=30)
        t1=time.perf_counter()
        await ws.send(json.dumps({"type":"start","voice":args.profile}))
        msg=json.loads(await asyncio.wait_for(ws.recv(),30))
        t2=time.perf_counter()
        if msg.get('event')!='started': raise RuntimeError(str(msg))
        conn_ms.append((t1-t0)*1000); start_ms.append((t2-t0)*1000)
        return ws
    # open sessions
    sem=asyncio.Semaphore(64)
    async def open_lim():
        async with sem: return await open_one()
    conns=await asyncio.gather(*[open_lim() for _ in range(args.sessions)])
    free=asyncio.Queue()
    for ws in conns: free.put_nowait(ws)
    results=[]; errors=0; inflight=0; done_ev=asyncio.Event()
    stop=time.monotonic()+args.duration
    async def do_req(ws):
        nonlocal errors
        r=await worker(ws,args.url,args.profile,args.text,args.mf,args.timeout,True)
        if 'ms' in r: results.append(r['ms'])
        else: errors+=1
        free.put_nowait(ws)
    tasks=[]
    t0=time.monotonic(); next_t=t0
    while next_t < stop:
        now=time.monotonic()
        if now < next_t: await asyncio.sleep(min(next_t-now,0.01))
        try:
            ws=await asyncio.wait_for(free.get(), timeout=max(0, stop-time.monotonic())+0.5)
        except Exception:
            errors+=1; next_t += random.expovariate(args.rate); continue
        tasks.append(asyncio.create_task(do_req(ws)))
        next_t += random.expovariate(args.rate)
    # wait running
    await asyncio.gather(*tasks, return_exceptions=True)
    elapsed=time.monotonic()-t0
    # close
    for ws in conns:
        try: await ws.close()
        except: pass
    out={'mode':'preconnected_poisson','sessions':args.sessions,'rate':args.rate,'duration':args.duration,'count':len(tasks),
         'completed':len(results),'errors':errors,'rows_per_s':len(results)/elapsed if elapsed>0 else 0,'elapsed_s':elapsed,
         'first_byte':pstats(results),'connect':pstats(conn_ms),'started':pstats(start_ms)}
    with open(args.out,'w') as f: json.dump(out,f,indent=2)
    print(json.dumps(out,indent=2))

if __name__=='__main__': asyncio.run(main())
