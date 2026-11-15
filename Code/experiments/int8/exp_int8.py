"""Isolated INT8 experiment: dynamic quantization timing + sample audio."""
import json, logging, os, sys, time
from pathlib import Path
import torch
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Code"))
sys.path.insert(0, str(REPO / "Code" / "probes"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)
OUT = REPO / "Code" / "experiments" / "out"
OUT.mkdir(parents=True, exist_ok=True)

def log(msg, obj=None):
    print(msg, flush=True)
    rec = {"msg": msg}
    if obj is not None: rec["data"] = obj
    with open(OUT / "int8.jsonl", "a") as f: f.write(json.dumps(rec) + "\n")

try:
    import scipy.io.wavfile
    from pocket_tts import TTSModel
    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from bench_batch_server import make_texts, pct, first_sound_ms

    VOICE = REPO / "Code/probes/ref/voice.wav"
    texts = make_texts(32)
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model); model.temp = 0.3
    sr = model.config.mimi.sample_rate; spf = int(round(sr / model.mimi.frame_rate))
    stream = BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16)
    stream.save_voice_profile(str(OUT / "int8_voice.pt"), conditioned=True)
    s_base = BatchedStream(model, voice_profile=str(OUT / "int8_voice.pt"), max_first_tokens=16, compact=True)
    s_base.stream(texts[:4], max_frames=4); torch.cuda.synchronize()

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

    base = measure(s_base, 32, 3)
    log("baseline", base)

    # sample audio baseline
    s_base2 = BatchedStream(model, voice_profile=str(OUT / "int8_voice.pt"), max_first_tokens=None, compact=True)
    a = s_base2.stream([texts[0]])[0].detach().cpu().numpy()
    scipy.io.wavfile.write(OUT / "int8_baseline.wav", sr, a)

    result = {"baseline": base, "int8": None, "method": None, "error": None}
    # try dynamic quantization on Linear (CPU-friendly API; apply on copy of flow_lm parts if possible)
    try:
        import copy
        m2 = copy.deepcopy(model)
        # torch dynamic quant works on CPU modules; try moving flow_lm to cpu quantize linear then back? risky.
        # safer: torchao int8 weight-only if available
        try:
            from torchao.quantization import quantize_, int8_weight_only
            quantize_(m2.flow_lm, int8_weight_only())
            m2 = m2.to("cuda").eval()
            enable_fp16_backbone(m2)
            s_i = BatchedStream(m2, voice_profile=str(OUT / "int8_voice.pt"), max_first_tokens=16, compact=True)
            s_i.stream(texts[:4], max_frames=4); torch.cuda.synchronize()
            res_i = measure(s_i, 32, 3)
            s_i2 = BatchedStream(m2, voice_profile=str(OUT / "int8_voice.pt"), max_first_tokens=None, compact=True)
            ai = s_i2.stream([texts[0]])[0].detach().cpu().numpy()
            scipy.io.wavfile.write(OUT / "int8_torchao.wav", sr, ai)
            result.update({"int8": res_i, "method": "torchao.int8_weight_only(flow_lm)"})
            log("torchao_int8", res_i)
        except Exception as e:
            log("torchao_failed", {"err": str(e)})
            # fallback: torch dynamic quant on CPU for linear submodules (may not run on cuda)
            try:
                from torch.ao.quantization import quantize_dynamic
                m3 = copy.deepcopy(model).cpu()
                quantize_dynamic(m3.flow_lm, {torch.nn.Linear}, dtype=torch.qint8)
                # run on CPU small sample
                m3.eval()
                # cannot use BatchedStream cuda path easily; just report quantized model created
                result.update({"int8": None, "method": "torch.ao.quantization dynamic qint8 on CPU (cuda path incompatible)", "error": str(e)})
                log("dynamic_cpu_quant_only", {"note": "applied on CPU copy"})
            except Exception as e2:
                result["error"] = f"torchao:{e}; dynamic:{e2}"
                log("int8_failed", {"err": result["error"]})
    except Exception as e:
        result["error"] = str(e)
        log("int8_error", {"err": str(e)})

    (OUT / "int8_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print("INT8_DONE", json.dumps(result))
except Exception as e:
    err = {"fatal": str(e)}
    (OUT / "int8_summary.json").write_text(json.dumps(err, indent=2) + "\n")
    print("INT8_FATAL", e)
    raise
