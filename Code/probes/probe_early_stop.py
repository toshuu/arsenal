import os, json, time, sys, asyncio, wave, numpy as np
os.environ['CUDA_VISIBLE_DEVICES']='0'
os.environ['ARSENAL_DEBUG']='1'
os.environ['ARSENAL_POCKET_TTS']='/kaggle/working/pocket-tts'
os.environ['ARSENAL_MODEL_DIR']='/kaggle/working/arsenal/Code/model'
for k,v in [('ARSENAL_MAX_QUEUE','4096'),('ARSENAL_MAX_ROWS','640'),('ARSENAL_MAX_BATCH','640'),('ARSENAL_BATCH_TARGET','640'),
            ('ARSENAL_CALL_FIRST_QUIET_MS','3'),('ARSENAL_CALL_FIRST_HARD_CAP_MS','40'),('ARSENAL_CALL_POISSON','0')]:
    os.environ[k]=v
sys.path.insert(0,'Code')
from fastapi.testclient import TestClient
from batch.server import create_app
from batch.job_classes import JobClass

TEXT="Hello, can you hear me now?"
OUT='Code/probes/out'

def p50(vals):
    vals=[v for v in vals if isinstance(v,(int,float))]
    if not vals: return None
    s=sorted(vals); return s[len(s)//2]
def p95(vals):
    vals=[v for v in vals if isinstance(v,(int,float))]
    if not vals: return None
    s=sorted(vals); return s[min(len(s)-1,int(len(s)*0.95))]

async def run_batch(worker, rows, mf, collect_audio=False):
    jobs=[]
    for _ in range(rows):
        jobs.append(worker.submit([TEXT], mf, None, job_class=JobClass.CALL_FIRST, mode='call'))
    results=await asyncio.gather(*[asyncio.wrap_future(j.future) for j in jobs])
    j=jobs[0]; t=j.t
    def dt(a,b): return (b-a)/1e6 if a and b else None
    bs=t.get('batch_start'); fe=t.get('first_emit'); se=t.get('synth_end')
    fes=[(jj.t.get('first_emit',0)-jj.t.get('batch_start',0))/1e6 for jj in jobs if jj.t.get('first_emit') and jj.t.get('batch_start')]
    out={'rows':rows,'mf':mf,'batch_wall_p50':None,'first_emit_batch':dt(bs,fe),'first_emit_stream_p50':p50(fes),'synth_end':dt(bs,se)}
    out['batch_wall'] = dt(bs,se)
    if collect_audio:
        out['audio0']=results[0][0]
    return out

app=create_app()
with TestClient(app) as client:
    for i in range(300):
        if client.get('/health').json().get('ready'): print('ready',flush=True); break
        time.sleep(1)
    worker=app.state.worker
    summary={}
    for mf in [16,8]:
        for _ in range(3): asyncio.run(run_batch(worker,224,mf))
        runs=[asyncio.run(run_batch(worker,224,mf)) for _ in range(20)]
        summary[str(mf)]={
            'mf':mf,'rows':224,
            'batch_wall_p50':p50([r['batch_wall'] for r in runs]),
            'batch_wall_p95':p95([r['batch_wall'] for r in runs]),
            'first_emit_batch_p50':p50([r['first_emit_batch'] for r in runs]),
            'first_emit_stream_p50':p50([r['first_emit_stream_p50'] for r in runs]),
        }
        print('MF',mf,summary[str(mf)],flush=True)

    # continuity samples: full call streams (first chunk mf + continuations) via WS-like internal? easier use debug/callramp? no, want audio.
    # use _one_call logic? we need audio bytes; easier use /ws/tts through TestClient
    import io
    def save_call_wav(name, text, first_frames):
        chunks=[]
        with client.websocket_connect('/ws/tts') as ws:
            ws.send_json({'type':'start'})
            ws.receive_json()
            ws.send_json({'type':'text','text':text,'max_frames':192})
            # but we need to control first chunk frames: server uses ARSENAL_CALL_FIRST_MAX_FRAMES env? in ws_tts: first_frames=min(int(os.getenv("ARSENAL_CALL_FIRST_MAX_FRAMES","32")), max_frames)
            done=0
            # text splits into 1 chunk for this short text? "Hello, can you hear me now?" -> first_clause whole thing, fits in 8 frames? 11 tokens, 6 words, should fit.
            while done<1:
                msg=ws.receive()
                if 'bytes' in msg and msg['bytes'] is not None: chunks.append(msg['bytes'])
                elif 'text' in msg and msg['text'] is not None:
                    ev=json.loads(msg['text'])
                    if ev.get('event')=='chunk_done': done+=1
                    if ev.get('event')=='error': print('ERR',ev); break
            ws.send_json({'type':'flush'})
            try: ws.receive_json()
            except: pass
        pcm=b''.join(chunks)
        with wave.open(f'{OUT}/{name}','wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        return {'file':name,'bytes':len(pcm),'samples':len(pcm)//2,'chunks':len(chunks)}

    # generate with env var control
    for mf in [16,8]:
        os.environ['ARSENAL_CALL_FIRST_MAX_FRAMES']=str(mf)
        # need server to pick up? ws handler reads env each time
        files=[]
        for i in range(3):
            files.append(save_call_wav(f'call_first_mf{mf}_{i}.wav', TEXT, mf))
        summary[str(mf)]['wav_samples']=files
        print('WAV',mf,files,flush=True)

    with open(f'{OUT}/early_stop_summary.json','w') as f: json.dump(summary,f,indent=2)
    print('saved summary',flush=True)
