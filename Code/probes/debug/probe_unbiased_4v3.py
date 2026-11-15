import os, sys, logging, time, json
from pathlib import Path
import torch
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'Code'))
sys.path.insert(0, str(REPO / 'Code' / 'probes'))
os.chdir(REPO / 'Code' / 'model')
logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from bench_batch_server import make_texts, pct, first_sound_ms

VOICE = REPO / 'Code' / 'probes' / 'ref' / 'voice.wav'
OUT = REPO / 'Code' / 'probes' / 'out' / 'probe_unbiased_4v3.json'
m = TTSModel.load_model(config='config.yaml').to('cuda').eval()
enable_fp16_backbone(m); m.temp = 0.3
sr = m.config.mimi.sample_rate; spf = int(round(sr / m.mimi.frame_rate))
texts = make_texts(128)
cfgs = {'3.0/16': (3.0, 16), '4.0/16': (4.0, 16)}
batches = [96, 128]
st = {k: BatchedStream(m, VOICE, voice_seconds=v, max_first_tokens=c) for k, (v, c) in cfgs.items()}
for s in st.values():
    s.stream(texts[:4], max_frames=4)
torch.cuda.synchronize()
res = {k: {b: [] for b in batches} for k in cfgs}
for rnd in range(5):
    for b in batches:
        order = ['3.0/16', '4.0/16'] if (rnd + b) % 2 == 0 else ['4.0/16', '3.0/16']
        for k in order:
            batch_texts = [texts[(rnd * 13 + r) % len(texts)] for r in range(b)]
            ft = [[] for _ in range(b)]
            t0 = time.perf_counter()
            def cb(row, chunk, elapsed, ft=ft, t0=t0): ft[row].append(time.perf_counter() - t0)
            audio = st[k].stream(batch_texts, on_chunk=cb)
            torch.cuda.synchronize()
            ms = [first_sound_ms(audio[r], ft[r], spf) for r in range(b)]
            ms = [x for x in ms if x is not None]
            res[k][b].append({'p50': round(pct(ms,50),1), 'p95': round(pct(ms,95),1), 'under': sum(1 for x in ms if x <= 350), 'n': len(ms)})
rows = []
for k in cfgs:
    for b in batches:
        bursts = res[k][b]
        all_p95 = [x['p95'] for x in bursts]
        all_under = sum(x['under'] for x in bursts)
        all_n = sum(x['n'] for x in bursts)
        rows.append({'cfg': k, 'batch': b, 'p50_med': round(pct([x['p50'] for x in bursts],50),1), 'p95_med': round(pct(all_p95,50),1), 'p95_max': round(max(all_p95),1), 'under': all_under, 'total': all_n, 'pct': round(100*all_under/all_n,1), 'bursts': bursts})
agg = {'probe': 'probe_unbiased_4v3', 'gpu_name': torch.cuda.get_device_name(0), 'results': rows}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(agg, indent=2) + '\n')
for r in rows:
    print(r['cfg'], 'B', r['batch'], 'p95_med', r['p95_med'], 'p95_max', r['p95_max'], 'pct', r['pct'])
print('UNBIASED_DONE')
