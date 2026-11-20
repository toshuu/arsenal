import os, json, time, sys, statistics
os.environ.setdefault('CUDA_VISIBLE_DEVICES','0')
os.environ.setdefault('ARSENAL_DEBUG','1')
os.environ.setdefault('ARSENAL_POCKET_TTS','/kaggle/working/pocket-tts')
os.environ.setdefault('ARSENAL_MODEL_DIR','/kaggle/working/arsenal/Code/model')
for k,v in [('ARSENAL_MAX_QUEUE','4096'),('ARSENAL_MAX_ROWS','640'),('ARSENAL_MAX_BATCH','640'),('ARSENAL_BATCH_TARGET','640'),('ARSENAL_CALL_FIRST_SUB_BATCH','640')]:
    os.environ.setdefault(k,v)
sys.path.insert(0,'Code')
from fastapi.testclient import TestClient
from batch.server import create_app

TEXT="Hello, can you hear me now?"
OUT='Code/probes/out'

def save(name,data):
    with open(f'{OUT}/{name}','w') as f: json.dump(data,f,indent=2)
    print('saved',name,flush=True)

app=create_app()
with TestClient(app) as client:
    for i in range(300):
        if client.get('/health').json().get('ready'): print('ready',flush=True); break
        time.sleep(1)
    metrics=app.state.metrics; worker=app.state.worker

    def run_burst(B,Q,H,warmups=2):
        os.environ['ARSENAL_CALL_FIRST_QUIET_MS']=str(Q)
        os.environ['ARSENAL_CALL_FIRST_HARD_CAP_MS']=str(H)
        os.environ['ARSENAL_BATCH_WINDOW_MS']='5'
        os.environ['ARSENAL_CALL_FIRST_SUB_BATCH']=str(B) # not used in quiet mode? limit becomes max_batch cap; quiet computes target
        os.environ['ARSENAL_CALL_FIRST_MAX_BATCH']=str(max(B,224))
        os.environ['ARSENAL_MAX_BATCH']=str(max(B,640))
        os.environ['ARSENAL_MAX_ROWS']=str(max(B,640))
        os.environ['ARSENAL_BATCH_TARGET']=str(B)
        worker.reload_config()
        url=lambda: f'/debug/callramp?b={B}&repeats=1&first_only=1&first_max_frames=16&window=5&text={TEXT.replace(" ","%20")}'
        # warmups
        for _ in range(warmups):
            client.get(url())
        bs0=list(metrics.batch_size); bw0=list(metrics.batch_wall_ms)
        r=client.get(url()).json()
        bs=list(metrics.batch_size)[len(bs0):]; bw=list(metrics.batch_wall_ms)[len(bw0):]
        run=r['runs'][0]
        return {
            'B':B,'Q':Q,'H':H,
            'batches':len(bs),'rows_per_batch':bs,'batch_wall_ms':[round(x,2) for x in bw],
            'first_byte_p50':run['first_byte_ms']['p50'],'first_byte_p95':run['first_byte_ms']['p95'],
            'errors':run['errors']
        }

    results=[]
    # quick baseline without quiet
    for B in [224,288,384]:
        os.environ.pop('ARSENAL_CALL_FIRST_QUIET_MS',None)
        os.environ.pop('ARSENAL_CALL_FIRST_HARD_CAP_MS',None)
        res=run_burst(B,0,0,warmups=2)
        res['mode']='no_quiet'
        results.append(res); print('RES',json.dumps(res),flush=True)

    for B in [224,288,384]:
        for Q in [1,2,3,5]:
            for H in [20,30,50]:
                res=run_burst(B,Q,H,warmups=2)
                res['mode']='quiet'
                results.append(res); print('RES',json.dumps(res),flush=True)
                save('admission_sweep_partial.json', results)
    save('admission_sweep.json', results)
print('DONE',flush=True)
