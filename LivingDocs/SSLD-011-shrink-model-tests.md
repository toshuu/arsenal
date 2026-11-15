<!-- ss-living-doc v1 -->
# SSLD-011: Shrink-model tests (multilingual-safe, sideline)

## STATE
doc_id: SSLD-011
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: none
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-011-shrink-model-tests.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-011-shrink-model-tests.md --sync

## RULES
<!-- rules:start -->
1. Run `next_command` from STATE. It prints your one task. Work only on that task.
2. Do the steps in order. After each step, change `[ ]` to `[x]`.
3. Touch only the file in `file:` and the files in `also_edit:`. Never touch other files.
4. Copy code blocks exactly. Do not improve them. Do not rename anything.
5. After the last step, run the command in `verify:`. Compare the output to `expect:`.
6. If the output matches: paste the first output line into `result:`, set `status: DONE`, then run `sync_command`.
7. If the output does not match: do `if_fail:`, then run `verify:` again. Try at most 2 times.
8. If it still fails, or if anything is unclear: set `status: BLOCKED`, write the reason in `blocked_reason:`, run `sync_command`, then STOP. Do not guess.
9. Never edit this RULES block. Never add, delete, or reorder tasks. Never invent results.
10. After `sync_command`, run `next_command` again. When STATE shows `status: DONE`, STOP.
<!-- rules:end -->

## TASKS

### T001: Inspect available pocket-tts models/variants
status: DONE
blocked_reason:
file: Code/experiments/shrink/check_models.py
context: Sideline. List installed pocket-tts version and available model/voice APIs for small/english variants (reference only; multilingual must be kept for main path).
do:
- [x] 1. CREATE `Code/experiments/shrink/check_models.py` with the code block below.

   ```python
   import importlib, inspect, json, pkgutil, sys
   out = {"python": sys.version}
   try:
       import pocket_tts
       out["pocket_tts_version"] = getattr(pocket_tts, "__version__", "unknown")
       out["pocket_tts_file"] = getattr(pocket_tts, "__file__", None)
       try:
           from pocket_tts import TTSModel
           out["TTSModel_attrs"] = [a for a in dir(TTSModel) if "load" in a.lower() or "model" in a.lower()]
           out["load_model_sig"] = str(inspect.signature(TTSModel.load_model))
       except Exception as e:
           out["TTSModel_err"] = str(e)
       try:
           import pocket_tts.models.tts_model as tm
           src = inspect.getsource(tm.TTSModel.load_model)
           out["load_model_src_head"] = "\n".join(src.splitlines()[:80])
       except Exception as e:
           out["src_err"] = str(e)
       names = [m.name for m in pkgutil.walk_packages(pocket_tts.__path__, pocket_tts.__name__ + ".")]
       out["submodules_sample"] = names[:80]
   except Exception as e:
       out["err"] = str(e)
   open("Code/experiments/out/check_models.json","w").write(json.dumps(out, indent=2))
   print("CHECK_DONE")
   print(out.get("pocket_tts_version"))
   ```

- [x] 2. RUN `python Code/experiments/shrink/check_models.py`.

verify: `python -c "import json,os; print(os.path.exists('Code/experiments/out/check_models.json'))"`
expect: `True`
if_fail: Read traceback. Fix copied script only. Run `verify:` again.
result: CHECK_DONE

### T002: Baseline multilingual component timing (current model)
status: DONE
blocked_reason:
file: Code/experiments/shrink/probe_current_breakdown.py
context: Sideline reference. Measure TTFA component timing on current multilingual model at B=32,128 (cond profile path).
do:
- [x] 1. CREATE `Code/experiments/shrink/probe_current_breakdown.py` with the code block below.

   ```python
   import sys, os, json, logging, time
   sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
   os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
   import torch
   from pocket_tts import TTSModel
   from batch.batched_stream import BatchedStream, set_state_padding, _clone_state_to_batch
   from batch.fp16 import enable_fp16_backbone
   from bench_batch_server import make_texts
   from pocket_tts.modules.stateful_module import init_states, increment_steps
   def sync(): torch.cuda.synchronize()
   model=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(model); model.temp=0.3
   VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'; prof='/kaggle/working/arsenal/Code/experiments/out/shrink_cur_voice.pt'
   sp0=BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16); sp0.save_voice_profile(prof, conditioned=True)
   out=[]
   for B in [32,128]:
       texts=make_texts(B); sp=BatchedStream(model, voice_profile=prof, voice_seconds=4.0, max_first_tokens=16, compact=True)
       sync(); t_all=time.perf_counter(); text_batch,text_pad,token_counts=sp._build_text_batch(texts); sync(); t_text=time.perf_counter()
       vlen=sp._voice_state_len(); max_frames=20; seq_len=vlen+text_batch.shape[1]+max_frames+4
       state=_clone_state_to_batch(sp.voice_state,B,seq_len,sp.device); set_state_padding(state,text_pad)
       mimi_steps=int(model.mimi.encoder_frame_rate/model.mimi.frame_rate); mimi_state=init_states(model.mimi,B,(max_frames+4)*mimi_steps); sync(); t_state=time.perf_counter()
       empty_tokens=torch.empty(B,0,dtype=torch.int64,device=sp.device); empty_latents=torch.empty(B,0,model.flow_lm.ldim,dtype=text_batch.dtype,device=sp.device)
       model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=empty_latents,audio_conditioning=text_batch); sync(); t_cond=time.perf_counter()
       latent=model.flow_lm.bos_emb.view(1,1,-1).expand(B,1,-1); empty_audio=torch.empty(B,0,model.flow_lm.dim,dtype=text_batch.dtype,device=sp.device)
       sync(); t=time.perf_counter(); latent,is_eos=model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=latent,audio_conditioning=empty_audio); sync(); flow0=(time.perf_counter()-t)*1000
       sync(); t=time.perf_counter(); decode_input=latent*model.flow_lm.emb_std+model.flow_lm.emb_mean; _=model.mimi.decode_from_latent(decode_input,mimi_state); increment_steps(model.mimi,mimi_state,increment=mimi_steps); sync(); mimi0=(time.perf_counter()-t)*1000; t_first=time.perf_counter()
       step_ms=[]; dec_ms=[]
       for i in range(1,8):
           sync(); t=time.perf_counter(); latent,is_eos=model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=latent,audio_conditioning=empty_audio); sync(); step_ms.append((time.perf_counter()-t)*1000)
           sync(); t=time.perf_counter(); decode_input=latent*model.flow_lm.emb_std+model.flow_lm.emb_mean; _=model.mimi.decode_from_latent(decode_input,mimi_state); increment_steps(model.mimi,mimi_state,increment=mimi_steps); sync(); dec_ms.append((time.perf_counter()-t)*1000)
       out.append({'B':B,'prep_text_ms':round((t_text-t_all)*1000,2),'state_ms':round((t_state-t_text)*1000,2),'cond_ms':round((t_cond-t_state)*1000,2),'flow0_ms':round(flow0,2),'mimi0_ms':round(mimi0,2),'ttfa_compute_ms':round((t_first-t_all)*1000,2),'flow_avg_ms':round(sum(step_ms)/len(step_ms),2),'mimi_avg_ms':round(sum(dec_ms)/len(dec_ms),2)})
   open('Code/experiments/out/shrink_current_breakdown.json','w').write(json.dumps(out,indent=2)); print('BREAKDOWN_DONE')
   ```

- [x] 2. RUN `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python Code/experiments/shrink/probe_current_breakdown.py`.

verify: `python -c "import json; d=json.load(open('Code/experiments/out/shrink_current_breakdown.json')); print(len(d)==2 and d[1]['B']==128)"`
expect: `True`
if_fail: Read traceback. Fix copied script only. Run `verify:` again.
result: BREAKDOWN_DONE

### T003: Try english small variants as reference (speed/B upper bound)
status: DONE
blocked_reason:
file: Code/experiments/shrink/probe_english_variants.py
context: Sideline reference only (English-only, not for multilingual main path). Attempt load/run english_18m/7m/2m or available small variants if supported by installed pocket-tts.
do:
- [x] 1. CREATE `Code/experiments/shrink/probe_english_variants.py` with the code block below.

   ```python
   import sys, os, json, logging, time, traceback
   sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
   os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
   import torch
   from pocket_tts import TTSModel
   from batch.batched_stream import BatchedStream
   from batch.fp16 import enable_fp16_backbone
   from bench_batch_server import make_texts, pct, first_sound_ms
   VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'
   variants=['english_18m_2026-10','english_18m_refl_2026-10','english_7m_2026-10','english_2m_2026-10']
   out={'variants':[],'note':'English-only reference; not multilingual-safe for main path.'}
   def measure(model,B=32,rounds=2):
       enable_fp16_backbone(model); model.temp=0.3
       sr=model.config.mimi.sample_rate; spf=int(round(sr/model.mimi.frame_rate))
       sp=BatchedStream(model,voice=VOICE,voice_seconds=4.0,max_first_tokens=16)
       prof='/kaggle/working/arsenal/Code/experiments/out/shrink_var_voice.pt'; sp.save_voice_profile(prof,conditioned=True)
       s=BatchedStream(model,voice_profile=prof,max_first_tokens=16,compact=True); texts=make_texts(B)
       s.stream(texts[:4],max_frames=4); torch.cuda.synchronize()
       all_ms=[]
       for rnd in range(rounds):
           bt=[texts[(rnd*13+r)%len(texts)] for r in range(B)]; ft=[[] for _ in range(B)]; t0=time.perf_counter()
           def cb(r,c,e,ft=ft,t0=t0): ft[r].append(time.perf_counter()-t0)
           audio=s.stream(bt,on_chunk=cb); torch.cuda.synchronize()
           for r in range(B):
               ms=first_sound_ms(audio[r],ft[r],spf);
               if ms is not None: all_ms.append(ms)
       return {'B':B,'p50':round(pct(all_ms,50),2),'p95':round(pct(all_ms,95),2),'n':len(all_ms)}
   for v in variants:
       rec={'variant':v}
       try:
           try:
               m=TTSModel.load_model(variant=v)
           except TypeError:
               try: m=TTSModel.load_model(model_name=v)
               except TypeError: m=TTSModel.load_model(v)
           m=m.to('cuda').eval(); rec['measure']=measure(m,32,2); rec['ok']=True
       except Exception as e:
           rec['ok']=False; rec['err']=str(e)[:300]
       out['variants'].append(rec); open('Code/experiments/out/shrink_english_variants.json','w').write(json.dumps(out,indent=2))
       torch.cuda.empty_cache()
   print('VARIANTS_DONE')
   ```

- [x] 2. RUN `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python Code/experiments/shrink/probe_english_variants.py`.

verify: `python -c "import json,os; d=json.load(open('Code/experiments/out/shrink_english_variants.json')); print('variants' in d)"`
expect: `True`
if_fail: Read traceback. Keep partial results in json. Run `verify:` again.
result: VARIANTS_DONE

### T004: Decoder/flow component size and timing detail
status: DONE
blocked_reason:
file: Code/experiments/shrink/probe_components.py
context: Measure current model component params and per-call timing (flow_lm vs mimi decode) to quantify decoder-shrink opportunity for multilingual path.
do:
- [x] 1. CREATE `Code/experiments/shrink/probe_components.py` with the code block below.

   ```python
   import sys, os, json, logging, time
   sys.path.insert(0,'/kaggle/working/pocket-tts'); sys.path.insert(0,'/kaggle/working/arsenal/Code'); sys.path.insert(0,'/kaggle/working/arsenal/Code/probes')
   os.chdir('/kaggle/working/arsenal/Code/model'); logging.disable(logging.CRITICAL)
   import torch
   from pocket_tts import TTSModel
   from batch.batched_stream import BatchedStream, set_state_padding, _clone_state_to_batch
   from batch.fp16 import enable_fp16_backbone
   from bench_batch_server import make_texts
   from pocket_tts.modules.stateful_module import init_states, increment_steps
   def count(m):
       try: return sum(p.numel() for p in m.parameters())
       except: return None
   model=TTSModel.load_model(config='config.yaml').to('cuda').eval(); enable_fp16_backbone(model); model.temp=0.3
   VOICE='/kaggle/working/arsenal/Code/probes/ref/voice.wav'; prof='/kaggle/working/arsenal/Code/experiments/out/shrink_comp_voice.pt'
   sp0=BatchedStream(model, voice=VOICE, voice_seconds=4.0, max_first_tokens=16); sp0.save_voice_profile(prof, conditioned=True)
   B=128; texts=make_texts(B); sp=BatchedStream(model, voice_profile=prof, voice_seconds=4.0, max_first_tokens=16, compact=True)
   text_batch,text_pad,_=sp._build_text_batch(texts); vlen=sp._voice_state_len(); max_frames=12; seq_len=vlen+text_batch.shape[1]+max_frames+4
   state=_clone_state_to_batch(sp.voice_state,B,seq_len,sp.device); set_state_padding(state,text_pad)
   mimi_steps=int(model.mimi.encoder_frame_rate/model.mimi.frame_rate); mimi_state=init_states(model.mimi,B,(max_frames+4)*mimi_steps)
   empty_tokens=torch.empty(B,0,dtype=torch.int64,device=sp.device); empty_latents=torch.empty(B,0,model.flow_lm.ldim,dtype=text_batch.dtype,device=sp.device)
   model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=empty_latents,audio_conditioning=text_batch)
   latent=model.flow_lm.bos_emb.view(1,1,-1).expand(B,1,-1); empty_audio=torch.empty(B,0,model.flow_lm.dim,dtype=text_batch.dtype,device=sp.device)
   torch.cuda.synchronize(); t=time.perf_counter(); latent,_=model._run_flow_lm_and_increment_step(model_state=state,text_tokens=empty_tokens,backbone_input_latents=latent,audio_conditioning=empty_audio); torch.cuda.synchronize(); flow_ms=(time.perf_counter()-t)*1000
   torch.cuda.synchronize(); t=time.perf_counter(); decode_input=latent*model.flow_lm.emb_std+model.flow_lm.emb_mean; _=model.mimi.decode_from_latent(decode_input,mimi_state); torch.cuda.synchronize(); mimi_ms=(time.perf_counter()-t)*1000
   out={
     'params':{
       'flow_lm':count(model.flow_lm),'mimi':count(getattr(model,'mimi',None)),'total':count(model),
       'mimi_encoder':count(getattr(model.mimi,'encoder',None)),'mimi_decoder':count(getattr(model.mimi,'decoder',None))
     },
     'timing_B128_ms':{'flow_step':round(flow_ms,2),'mimi_decode':round(mimi_ms,2)},
     'note':'Decoder shrink highest leverage for multilingual (decode-bound at B). English small models reference only.'
   }
   open('Code/experiments/out/shrink_components.json','w').write(json.dumps(out,indent=2)); print('COMP_DONE')
   ```

- [x] 2. RUN `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python Code/experiments/shrink/probe_components.py`.

verify: `python -c "import json; d=json.load(open('Code/experiments/out/shrink_components.json')); print(d['timing_B128_ms']['mimi_decode'] is not None)"`
expect: `True`
if_fail: Read traceback. Fix copied script only. Run `verify:` again.
result: COMP_DONE

### T005: Record facts and close sideline
status: DONE
blocked_reason:
file: .stageset/facts.md
also_edit: LivingDocs/SSLD-011-shrink-model-tests.md
context: Summarize findings (multilingual-safe opportunities, english-reference results). Set SSLD status DONE if T001-T004 DONE, else BLOCKED with reason.
do:
- [x] 1. APPEND fact row(s) for SSLD-011 results (current breakdown, components, english-variant availability/perf).
- [x] 2. RUN `python scripts/stageset-status.py --sync`.

verify: `python scripts/stageset-status.py --validate`
expect: `StageSet validation passed.`
if_fail: Fix metadata/content issues. Run `verify:` again.
result: FACT-0042
