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
