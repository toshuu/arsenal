<!-- ss-living-doc v1 -->
# SSLD-002: Probe the Pocket TTS multilingual model

## STATE
doc_id: SSLD-002
status: DONE
current_task: T004
tasks_done: 4
tasks_total: 4
skeleton: Skeletons/Probes/probe_model.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-002-probe-model.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-002-probe-model.md --sync

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

### T001: Create probe_model.py
status: DONE
blocked_reason:
file: Code/probes/probe_model.py
context: Setup is done: SSLD-001 is DONE and Code/model has the model files. This task creates the read-only probe script. Do not run it yet.
do:
- [x] 1. CREATE `Code/probes/probe_model.py` with the code block below. Create the folder `Code/probes` if it does not exist.

   ```python
   """Read-only probe for pocket-tts-multilingual.

   Writes one JSON file: Code/probes/out/probe_model.json.
   Changes no project file except files in Code/probes/out/.
   """
   import copy
   import inspect
   import json
   import math
   import os
   import platform
   import struct
   import sys
   import time
   import traceback
   import wave
   from pathlib import Path

   HERE = Path(__file__).resolve().parent
   MODEL_DIR = HERE.parent / "model"
   OUT_DIR = HERE / "out"
   REF_WAV = HERE / "ref" / "voice.wav"
   SILENCE_THRESHOLD = 0.01
   TEST_TEXT = "Hello, this is a short test sentence."
   MAX_TREE_DEPTH = 3
   MAX_ITEMS = 60


   def need_model(ctx):
       if ctx.get("model") is None:
           raise RuntimeError("model not loaded: " + str(ctx.get("load_error")))
       return ctx["model"]


   def safe_sig(fn):
       try:
           return str(inspect.signature(fn))
       except Exception as exc:
           return "UNAVAILABLE: " + repr(exc)


   def module_tree(module, depth):
       items = []
       for name, child in module.named_children():
           entry = {
               "name": name,
               "class": type(child).__name__,
               "params": sum(p.numel() for p in child.parameters()),
           }
           if depth + 1 < MAX_TREE_DEPTH:
               entry["children"] = module_tree(child, depth + 1)
           items.append(entry)
           if len(items) >= MAX_ITEMS:
               break
       return items


   def walk_tensors(obj, path, acc):
       import torch

       if isinstance(obj, torch.Tensor):
           acc["count"] += 1
           acc["bytes"] += obj.numel() * obj.element_size()
           acc["dtypes"].add(str(obj.dtype))
           if len(acc["examples"]) < MAX_ITEMS:
               acc["examples"].append(
                   {"path": path, "shape": list(obj.shape), "dtype": str(obj.dtype)}
               )
       elif isinstance(obj, dict):
           for key, value in obj.items():
               walk_tensors(value, path + "/" + str(key), acc)
       elif isinstance(obj, (list, tuple)):
           for index, value in enumerate(obj):
               walk_tensors(value, path + "/" + str(index), acc)


   def write_sine_wav(path, seconds=3, rate=24000):
       path.parent.mkdir(parents=True, exist_ok=True)
       with wave.open(str(path), "wb") as handle:
           handle.setnchannels(1)
           handle.setsampwidth(2)
           handle.setframerate(rate)
           frames = bytearray()
           for i in range(seconds * rate):
               value = int(8000 * math.sin(2 * math.pi * 220 * i / rate))
               frames += struct.pack("<h", value)
           handle.writeframes(bytes(frames))


   def fresh_state(ctx):
       state = ctx.get("state")
       if state is None:
           raise RuntimeError("no voice state: the voice section failed")
       try:
           return copy.deepcopy(state)
       except Exception:
           return state


   def probe_env(ctx):
       import importlib.metadata as md

       out = {
           "python": sys.version.split()[0],
           "platform": platform.platform(),
           "cpu_count": os.cpu_count(),
       }
       versions = {}
       for name in ["pocket-tts", "torch", "numpy", "huggingface_hub", "safetensors", "sentencepiece"]:
           try:
               versions[name] = md.version(name)
           except Exception:
               versions[name] = "NOT_INSTALLED"
       out["versions"] = versions
       try:
           import torch

           out["cuda_available"] = bool(torch.cuda.is_available())
           out["cuda_runtime"] = torch.version.cuda
           out["torch_num_threads"] = torch.get_num_threads()
           if torch.cuda.is_available():
               props = torch.cuda.get_device_properties(0)
               out["gpu"] = {
                   "name": props.name,
                   "total_memory_mb": props.total_memory // (1024 * 1024),
                   "capability": list(torch.cuda.get_device_capability(0)),
               }
       except Exception as exc:
           out["torch_error"] = repr(exc)
       try:
           import subprocess

           result = subprocess.run(
               ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
               capture_output=True,
               text=True,
               timeout=20,
           )
           out["nvidia_smi"] = (result.stdout or result.stderr).strip()
       except Exception as exc:
           out["nvidia_smi"] = "UNAVAILABLE: " + repr(exc)
       return out


   def load_model(ctx):
       try:
           from pocket_tts import TTSModel

           start = time.perf_counter()
           ctx["model"] = TTSModel.load_model(config="config.yaml")
           ctx["load_seconds"] = round(time.perf_counter() - start, 3)
       except Exception:
           ctx["model"] = None
           ctx["load_error"] = traceback.format_exc()[-1500:]


   def probe_arch(ctx):
       model = need_model(ctx)
       params = list(model.named_parameters())
       out = {
           "class": type(model).__name__,
           "total_params": sum(p.numel() for _, p in params),
           "dtypes": sorted({str(p.dtype) for _, p in params}),
           "device": str(params[0][1].device) if params else None,
           "load_seconds": ctx.get("load_seconds"),
           "children": module_tree(model, 0),
       }
       scalars = {}
       for name in dir(model):
           if name.startswith("_"):
               continue
           try:
               value = getattr(model, name)
           except Exception:
               continue
           if isinstance(value, (int, float, str, bool)):
               scalars[name] = value
       out["scalar_attributes"] = scalars
       config_path = MODEL_DIR / "config.yaml"
       out["config_yaml"] = config_path.read_text(encoding="utf-8")[:8000]
       return out


   def probe_voice(ctx):
       model = need_model(ctx)
       if REF_WAV.exists():
           ref, source = REF_WAV, "real"
       else:
           ref, source = OUT_DIR / "ref_synthetic.wav", "synthetic"
           write_sine_wav(ref)
       start = time.perf_counter()
       state = model.get_state_for_audio_prompt(str(ref))
       seconds = round(time.perf_counter() - start, 4)
       ctx["state"] = state
       acc = {"count": 0, "bytes": 0, "examples": [], "dtypes": set()}
       walk_tensors(state, "", acc)
       out = {
           "voice_source": source,
           "prompt_seconds": seconds,
           "state_type": type(state).__name__,
           "top_level_keys": [str(k) for k in list(state.keys())[:MAX_ITEMS]] if isinstance(state, dict) else None,
           "tensor_count": acc["count"],
           "tensor_bytes": acc["bytes"],
           "tensor_mb": round(acc["bytes"] / (1024 * 1024), 3),
           "tensor_dtypes": sorted(acc["dtypes"]),
           "examples": acc["examples"],
       }
       try:
           start = time.perf_counter()
           copy.deepcopy(state)
           out["deepcopy_ok"] = True
           out["deepcopy_seconds"] = round(time.perf_counter() - start, 4)
       except Exception as exc:
           out["deepcopy_ok"] = False
           out["deepcopy_error"] = repr(exc)
       return out


   def probe_stream(ctx):
       model = need_model(ctx)
       out = {"sample_rate": getattr(model, "sample_rate", None)}
       for name in ["generate_audio", "generate_audio_stream", "get_state_for_audio_prompt"]:
           fn = getattr(model, name, None)
           out[name] = {"exists": fn is not None, "signature": safe_sig(fn) if fn else None}
       out["public_methods"] = sorted(
           n for n in dir(model) if not n.startswith("_") and callable(getattr(model, n, None))
       )[:MAX_ITEMS]
       stream_fn = getattr(model, "generate_audio_stream", None)
       if stream_fn is None:
           out["streaming_run"] = "SKIPPED: no generate_audio_stream"
           return out
       state = fresh_state(ctx)
       start = time.perf_counter()
       first_seconds = None
       chunks = []
       total_samples = 0
       for chunk in stream_fn(state, TEST_TEXT):
           now = time.perf_counter() - start
           if first_seconds is None:
               first_seconds = now
           samples = int(chunk.numel())
           total_samples += samples
           if len(chunks) < 10:
               chunks.append({"t_seconds": round(now, 4), "samples": samples})
       out["streaming_run"] = {
           "time_to_first_chunk_ms": round(first_seconds * 1000, 1) if first_seconds is not None else None,
           "chunk_count_seen": len(chunks),
           "first_chunks": chunks,
           "total_samples": total_samples,
           "total_seconds": round(time.perf_counter() - start, 4),
       }
       return out


   def probe_silence(ctx):
       model = need_model(ctx)
       rate = int(getattr(model, "sample_rate"))
       model.generate_audio(fresh_state(ctx), TEST_TEXT)
       state = fresh_state(ctx)
       start = time.perf_counter()
       audio = model.generate_audio(state, TEST_TEXT)
       seconds = time.perf_counter() - start
       samples = audio.reshape(-1).abs()
       loud = (samples > SILENCE_THRESHOLD).nonzero()
       first = int(loud[0]) if len(loud) else None
       duration = samples.numel() / rate
       return {
           "silence_threshold": SILENCE_THRESHOLD,
           "num_samples": int(samples.numel()),
           "duration_seconds": round(duration, 3),
           "generate_seconds": round(seconds, 4),
           "rtf": round(seconds / duration, 4) if duration else None,
           "peak": float(samples.max()) if samples.numel() else None,
           "first_non_silent_sample": first,
           "leading_silence_ms": round(first * 1000 / rate, 1) if first is not None else None,
       }


   def probe_batch(ctx):
       model = need_model(ctx)
       names = set()
       for mod_name, mod in model.named_modules():
           for attr in dir(mod):
               if "batch" in attr.lower() and not attr.startswith("__"):
                   names.add((mod_name or "<root>") + "." + attr)
       params = []
       try:
           params = list(inspect.signature(model.generate_audio).parameters)
       except Exception as exc:
           params = ["UNAVAILABLE: " + repr(exc)]
       return {"batch_related_names": sorted(names)[:MAX_ITEMS], "generate_audio_params": params}


   def probe_codec(ctx):
       model = need_model(ctx)
       modules = {}
       streaming = {}
       for mod_name, mod in model.named_modules():
           label = mod_name or "<root>"
           cname = type(mod).__name__
           if any(k in cname.lower() for k in ("mimi", "codec", "stream", "decoder", "encoder")):
               if len(modules) < MAX_ITEMS:
                   modules[label] = cname
           for attr in dir(mod):
               if "stream" in attr.lower() and not attr.startswith("__"):
                   streaming.setdefault(attr, label)
       return {"codec_like_modules": modules, "streaming_names": dict(list(streaming.items())[:MAX_ITEMS])}


   def run_section(sections, name, fn, ctx):
       try:
           data = fn(ctx)
           sections[name] = data if isinstance(data, dict) else {"value": data}
       except Exception:
           sections[name] = {"error": traceback.format_exc()[-1500:]}


   def main():
       OUT_DIR.mkdir(parents=True, exist_ok=True)
       start_dir = os.getcwd()
       ctx = {}
       sections = {}
       try:
           if MODEL_DIR.is_dir():
               os.chdir(MODEL_DIR)
           run_section(sections, "env", probe_env, ctx)
           load_model(ctx)
           for name, fn in [
               ("arch", probe_arch),
               ("voice", probe_voice),
               ("stream", probe_stream),
               ("silence", probe_silence),
               ("batch", probe_batch),
               ("codec", probe_codec),
           ]:
               run_section(sections, name, fn, ctx)
       finally:
           os.chdir(start_dir)
       result = {
           "probe": "probe_model",
           "model_dir": str(MODEL_DIR),
           "load_error": ctx.get("load_error"),
           "silence_threshold": SILENCE_THRESHOLD,
           "test_text": TEST_TEXT,
           "sections": sections,
       }
       (OUT_DIR / "probe_model.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
       errors = sum(1 for s in sections.values() if "error" in s)
       print("PROBE_MODEL_DONE sections=%d errors=%d" % (len(sections), errors))
       return 0


   if __name__ == "__main__":
       sys.exit(main())
   ```
- [x] 2. CHECK that the file has valid Python syntax.
verify: `python -c "import ast; ast.parse(open('Code/probes/probe_model.py').read()); print('syntax ok')"`
expect: syntax ok
if_fail: Open `Code/probes/probe_model.py`. Make it match the code block in step 1 exactly. Run `verify:` again.
result: syntax ok

### T002: Run the probe
status: DONE
blocked_reason:
file: Code/probes/out/probe_model.json
context: Code/probes/probe_model.py exists. If Code/probes/ref/voice.wav exists, the probe uses it. If not, it uses a synthetic tone. This task runs the probe once.
do:
- [x] 1. RUN `python Code/probes/probe_model.py` from the repository root. It prints one line that starts with `PROBE_MODEL_DONE`.
- [x] 2. CHECK that the file `Code/probes/out/probe_model.json` exists.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_model.json')); print(len(d['sections']))"`
expect: 7
if_fail: Run the command in step 1 again. Then run `verify:` again.
result: 7

### T003: Check the probe sections
status: DONE
blocked_reason:
file: Code/probes/out/probe_model.json
context: The probe wrote the JSON file. Each of the 7 sections must have no `error` key. A section error means the probe found a real problem.
do:
- [x] 1. CHECK that no section in `Code/probes/out/probe_model.json` has an `error` key.
verify: `python -c "import json; d=json.load(open('Code/probes/out/probe_model.json')); print(sum(1 for s in d['sections'].values() if 'error' in s))"`
expect: 0
if_fail: Run `python Code/probes/probe_model.py` once more. Run `verify:` again. If the count is still not 0, copy the first `error` text from the JSON file into `blocked_reason:`.
result: 0

### T004: Update skeleton metadata
status: DONE
blocked_reason:
file: Skeletons/Probes/probe_model.md
context: The probe ran with no section errors. This task records that the code implements spec_revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_model.md`: find the text `implemented_revision: 0` and replace it with `implemented_revision: 1`.
- [x] 2. EDIT `Skeletons/Probes/probe_model.md`: find the text `status: READY` and replace it with `status: DONE`.
verify: `python -c "t=open('Skeletons/Probes/probe_model.md').read(); print(t.count('implemented_revision: 1'), t.count('status: DONE'))"`
expect: 1 1
if_fail: Open `Skeletons/Probes/probe_model.md`. Make the line with `implemented_revision:` end in 1. Make the line with `status:` end in DONE. Run `verify:` again.
result: 1 1
