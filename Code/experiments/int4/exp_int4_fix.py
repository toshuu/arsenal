"""Try INT4 fixes from web: hqq/tile_packed, dtype/packing variants. Incremental save."""
import json, logging, os, sys, time, copy, traceback
from pathlib import Path
import torch
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Code")); sys.path.insert(0, str(REPO / "Code" / "probes"))
os.chdir(REPO / "Code" / "model"); logging.disable(logging.CRITICAL)
OUT = REPO / "Code" / "experiments" / "out"; OUT.mkdir(parents=True, exist_ok=True)
JSONL = OUT / "int4_fix.jsonl"; SUM = OUT / "int4_fix_summary.json"
def log(msg,obj=None):
    print(msg,flush=True); rec={"msg":msg}
    if obj is not None: rec["data"]=obj
    open(JSONL,"a").write(json.dumps(rec)+"\n")
def save(d): tmp=SUM.with_suffix('.tmp'); tmp.write_text(json.dumps(d,indent=2)); tmp.replace(SUM)

result={"attempts":[],"best":None,"error":None}
try:
    import scipy.io.wavfile
    from pocket_tts import TTSModel
    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from bench_batch_server import make_texts, pct, first_sound_ms
    from torchao.quantization import quantize_, Int4WeightOnlyConfig
    try:
        from torchao.quantization import int4_weight_only
    except Exception:
        int4_weight_only=None

    VOICE = REPO / "Code/probes/ref/voice.wav"; texts = make_texts(32)
    base_model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    # keep fp32 copy for quant
    base_fp32 = copy.deepcopy(base_model).cpu().float().eval()
    enable_fp16_backbone(base_model); base_model.temp = 0.3
    sr = base_model.config.mimi.sample_rate; spf = int(round(sr / base_model.mimi.frame_rate))
    sp = BatchedStream(base_model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16)
    sp.save_voice_profile(str(OUT / "int4fix_voice.pt"), conditioned=True)
    def measure(s, B=32, rounds=3):
        all_ms=[]; walls=[]
        for rnd in range(rounds):
            bt=[texts[(rnd*13+r)%len(texts)] for r in range(B)]
            ft=[[] for _ in range(B)]; t0=time.perf_counter()
            def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
            audio=s.stream(bt,on_chunk=cb); torch.cuda.synchronize()
            walls.append(time.perf_counter()-t0)
            for r in range(B):
                ms=first_sound_ms(audio[r],ft[r],spf)
                if ms is not None: all_ms.append(ms)
        return {"p50":round(pct(all_ms,50),2),"p95":round(pct(all_ms,95),2),"wall_med":round(pct(walls,50),3),"under350":sum(1 for x in all_ms if x<=350),"n":len(all_ms)}
    s_base = BatchedStream(base_model, voice_profile=str(OUT / "int4fix_voice.pt"), max_first_tokens=16, compact=True)
    s_base.stream(texts[:4], max_frames=4); torch.cuda.synchronize()
    baseline=measure(s_base,32,3); result['baseline']=baseline; log('baseline',baseline); save(result)

    configs=[
        ("v2_plain_g64_hqq_fp32", lambda: Int4WeightOnlyConfig(group_size=64, int4_packing_format='plain', int4_choose_qparams_algorithm='hqq')),
        ("v2_tile_g64_hqq_fp32", lambda: Int4WeightOnlyConfig(group_size=64, int4_packing_format='tile_packed_to_4d', int4_choose_qparams_algorithm='hqq')),
        ("v2_tile_g32_hqq_fp32", lambda: Int4WeightOnlyConfig(group_size=32, int4_packing_format='tile_packed_to_4d', int4_choose_qparams_algorithm='hqq')),
        ("v2_plain_g64_tiny_fp32", lambda: Int4WeightOnlyConfig(group_size=64, int4_packing_format='plain', int4_choose_qparams_algorithm='tinygemm')),
        ("v1_g64_fp32", lambda: Int4WeightOnlyConfig(group_size=64, version=1) if 'version' in Int4WeightOnlyConfig.__init__.__code__.co_varnames else Int4WeightOnlyConfig(group_size=64)),
    ]
    for name,make_cfg in configs:
        try:
            m2=copy.deepcopy(base_fp32).eval()
            cfg=make_cfg()
            quantize_(m2.flow_lm, cfg)
            m2=m2.to('cuda').eval(); enable_fp16_backbone(m2)
            s_i = BatchedStream(m2, voice_profile=str(OUT / "int4fix_voice.pt"), max_first_tokens=16, compact=True)
            s_i.stream(texts[:4], max_frames=4); torch.cuda.synchronize()
            res_i = measure(s_i, 32, 3)
            s_i2 = BatchedStream(m2, voice_profile=str(OUT / "int4fix_voice.pt"), max_first_tokens=None, compact=True)
            ai = s_i2.stream([texts[0]])[0].detach().cpu().numpy(); scipy.io.wavfile.write(OUT / f"int4fix_{name}.wav", sr, ai)
            att={"name":name,"ok":True,"result":res_i}; result['attempts'].append(att); result['best']=att; log('ok',att); save(result)
            print("INT4FIX_DONE",json.dumps(result)); sys.exit(0)
        except Exception as e:
            att={"name":name,"ok":False,"err":str(e)[:400]}; result['attempts'].append(att); log('fail',att); save(result)
            try: torch.cuda.synchronize(); torch.cuda.empty_cache()
            except: pass
    print("INT4FIX_DONE",json.dumps(result))
except Exception as e:
    result['fatal']=str(e); result['tb']=traceback.format_exc(limit=3); save(result); print('INT4FIX_FATAL',e)
