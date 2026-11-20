import os, json, time, sys, statistics
os.environ.setdefault('CUDA_VISIBLE_DEVICES','0')
os.environ.setdefault('ARSENAL_DEBUG','1')
os.environ.setdefault('ARSENAL_POCKET_TTS','/kaggle/working/pocket-tts')
os.environ.setdefault('ARSENAL_MODEL_DIR','/kaggle/working/arsenal/Code/model')
for k,v in [('ARSENAL_MAX_QUEUE','4096'),('ARSENAL_MAX_ROWS','640'),('ARSENAL_MAX_BATCH','640'),('ARSENAL_BATCH_TARGET','640')]:
    os.environ[k]=v
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
    worker=app.state.worker
    allres={}
    for (Q,H) in [(2,40),(2,60),(2,100),(3,40),(3,60),(3,100),(5,40),(5,60),(5,100)]:
        key=f"Q{Q}_H{H}"; allres[key]={}
        os.environ['ARSENAL_CALL_FIRST_QUIET_MS']=str(Q)
        os.environ['ARSENAL_CALL_FIRST_HARD_CAP_MS']=str(H)
        os.environ['ARSENAL_CALL_POISSON']='0'
        for B in [224,288,384]:
            os.environ['ARSENAL_MAX_BATCH']=str(max(B,640))
            os.environ['ARSENAL_MAX_ROWS']=str(max(B,640))
            os.environ['ARSENAL_BATCH_TARGET']=str(B)
            os.environ['ARSENAL_CALL_FIRST_MAX_BATCH']=str(max(B,224))
            worker.reload_config()
            url=lambda: f'/debug/callramp?b={B}&repeats=1&first_only=1&first_max_frames=16&window=5&text={TEXT.replace(" ","%20")}'
            # cold
            r=client.get(url()).json(); run=r['runs'][0]
            cold={'p50':run['first_byte_ms']['p50'],'p95':run['first_byte_ms']['p95'],'batches':run.get('batch_sizes',[]),'errors':run['errors']}
            # 2 warmups
            client.get(url()); client.get(url())
            reps=[]
            for i in range(10):
                r=client.get(url()).json(); run=r['runs'][0]
                reps.append({'i':i,'p50':run['first_byte_ms']['p50'],'p95':run['first_byte_ms']['p95'],'batches':run.get('batch_sizes',[]),'errors':run['errors']})
            p50s=[x['p50'] for x in reps]; p95s=[x['p95'] for x in reps]
            spread=max(p95s)-min(p95s) if p95s else None
            one_batch=sum(1 for x in reps if len(x['batches'])==1)
            entry={'Q':Q,'H':H,'B':B,'cold':cold,'reps':reps,
                   'warm_p50_med':statistics.median(p50s),'warm_p95_med':statistics.median(p95s),
                   'spread_p95':spread,'one_batch':one_batch}
            allres[key][str(B)]=entry
            print(f"ENTRY Q={Q} H={H} B={B} cold_p95={cold['p95']:.2f} cold_batches={cold['batches']} warm_p95_med={entry['warm_p95_med']:.2f} spread={spread:.2f} one_batch={one_batch}/10", flush=True)
            save('qh_repeat_partial.json', allres)
    save('qh_repeat.json', allres)
    # print summary table
    print('\nTABLE')
    print('B | Q/H | batches per repeat | rows/batch examples | p50/p95 | spread | errors')
    for key in allres:
        Q=int(key.split('_')[0][1:]); H=int(key.split('_')[1][1:])
        for B in ['224','288','384']:
            e=allres[key].get(B)
            if not e: continue
            bcounts=[len(r['batches']) for r in e['reps']]
            rowsamps=[r['batches'] for r in e['reps'][:3]]
            errs=sum(r['errors'] for r in e['reps'])
            print(f"{B} | {Q}/{H} | {bcounts} | {rowsamps} | {e['warm_p50_med']:.2f}/{e['warm_p95_med']:.2f} | {e['spread_p95']:.2f} | {errs}")
print('DONE',flush=True)
