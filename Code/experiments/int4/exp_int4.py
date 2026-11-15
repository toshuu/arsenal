"""Sideline INT4 experiment: try torchao int4 weight-only on flow_lm."""
import json, logging, os, sys, time, copy, traceback
from pathlib import Path
import torch
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Code")); sys.path.insert(0, str(REPO / "Code" / "probes"))
os.chdir(REPO / "Code" / "model"); logging.disable(logging.CRITICAL)
OUT = REPO / "Code" / "experiments" / "out"; OUT.mkdir(parents=True, exist_ok=True)
JSONL = OUT / "int4.jsonl"; SUM = OUT / "int4_summary.json"
def log(msg,obj=None):
    print(msg,flush=True); rec={"msg":msg};
    if obj is not None: rec["data"]=obj
    with open(JSONL,"a") as f: f.write(json.dumps(rec)+"\n")
def save(d): tmp=SUM.with_suffix('.tmp'); tmp.write_text(json.dumps(d,indent=2)); tmp.replace(SUM)

result={"config":{"B":32,"voice_seconds":4.0,"cap":16,"rounds":3},"baseline":None,"int4":None,"method":None,"attempts":[],"error":None}
try:
    import scipy.io.wavfile
    from pocket_tts import TTSModel
    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from bench_batch_server import make_texts, pct, first_sound_ms

    VOICE = REPO / "Code/probes/ref/voice.wav"; texts = make_texts(32)
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model); model.temp = 0.3
    sr = model.config.mimi.sample_rate; spf = int(round(sr / model.mimi.frame_rate))
    stream = BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16)
    stream.save_voice_profile(str(OUT / "int4_voice.pt"), conditioned=True)

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

    s_base = BatchedStream(model, voice_profile=str(OUT / "int4_voice.pt"), max_first_tokens=16, compact=True)
    s_base.stream(texts[:4], max_frames=4); torch.cuda.synchronize()
    base = measure(s_base, 32, 3); log("baseline", base); result["baseline"]=base
    s_base2 = BatchedStream(model, voice_profile=str(OUT / "int4_voice.pt"), max_first_tokens=None, compact=True)
    a = s_base2.stream([texts[0]])[0].detach().cpu().numpy(); scipy.io.wavfile.write(OUT / "int4_baseline.wav", sr, a)
    save(result)

    from torchao.quantization import quantize_, Int4WeightOnlyConfig
    attempts=[
        ("cfg_g64_fp32", lambda m: (m.flow_lm.to(torch.float32), quantize_(m.flow_lm, Int4WeightOnlyConfig(group_size=64)))),
        ("cfg_g32_fp32", lambda m: (m.flow_lm.to(torch.float32), quantize_(m.flow_lm, Int4WeightOnlyConfig(group_size=32)))),
        ("cfg_g128_fp32", lambda m: (m.flow_lm.to(torch.float32), quantize_(m.flow_lm, Int4WeightOnlyConfig(group_size=128)))),
    ]
    for name,fn in attempts:
        try:
            m2=copy.deepcopy(model)
            fn(m2)
            m2=m2.to('cuda').eval(); enable_fp16_backbone(m2)
            s_i = BatchedStream(m2, voice_profile=str(OUT / "int4_voice.pt"), max_first_tokens=16, compact=True)
            s_i.stream(texts[:4], max_frames=4); torch.cuda.synchronize()
            res_i = measure(s_i, 32, 3); log("int4_ok",{name:res_i})
            s_i2 = BatchedStream(m2, voice_profile=str(OUT / "int4_voice.pt"), max_first_tokens=None, compact=True)
            ai = s_i2.stream([texts[0]])[0].detach().cpu().numpy(); scipy.io.wavfile.write(OUT / "int4_torchao.wav", sr, ai)
            result.update({"int4":res_i,"method":f"torchao.Int4WeightOnlyConfig {name}"}); result["attempts"].append({"name":name,"ok":True})
            save(result); print("INT4_DONE",json.dumps(result)); sys.exit(0)
        except Exception as e:
            tb=traceback.format_exc(limit=2)
            log("int4_attempt_fail",{"name":name,"err":str(e)})
            result["attempts"].append({"name":name,"ok":False,"err":str(e)[:300]}); save(result)
            # cuda context may be bad after kernel error
            try: torch.cuda.synchronize()
            except: pass
    result["error"]="all int4 attempts failed"
    save(result); print("INT4_DONE",json.dumps(result))
except Exception as e:
    result["error"]=str(e); save(result); print("INT4_FATAL",e); traceback.print_exc()
