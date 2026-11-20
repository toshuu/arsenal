"""Arsenal TTS Modal app: one T4, one bounded batch worker.

Deploy the serving app:
    modal deploy Code/deploy/modal_app.py

Build the voice cache and profiles once (dev app):
    modal run Code/deploy/modal_app.py::build_assets

Run helpers (dev app, does not stop the serving app):
    modal run Code/deploy/modal_app.py::probe
    modal run Code/deploy/modal_app.py::direct_bench --bs 32

Stop the serving app and the GPU when idle:
    modal app stop arsenal-tts-t4
"""

from __future__ import annotations

import modal

APP_NAME = "arsenal-tts-t4"
DEV_NAME = "arsenal-tts-dev"
CODE_DIR = "/root/arsenal/Code"
CACHE_DIR = "/cache"
PROFILES = f"{CACHE_DIR}/profiles"
VOICE_CACHE = f"{CACHE_DIR}/voice_cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1")
    .pip_install(
        "pocket-tts==4.0.1",
        "fastapi>=0.100",
        "uvicorn[standard]>=0.13",
        "httpx",
    )
    .add_local_dir("Code/batch", remote_path=f"{CODE_DIR}/batch")
    .add_local_dir("Code/model", remote_path=f"{CODE_DIR}/model")
    .add_local_dir("Code/probes/ref", remote_path=f"{CODE_DIR}/probes/ref")
    .add_local_file(
        "Code/probes/probe_http_load.py",
        remote_path=f"{CODE_DIR}/probes/probe_http_load.py",
    )
)

cache = modal.Volume.from_name("arsenal-tts-cache", create_if_missing=True)

app = modal.App(APP_NAME)
dev = modal.App(DEV_NAME)

common_env = {
    "PYTHONUNBUFFERED": "1",
    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
    "ARSENAL_MODEL_DIR": f"{CODE_DIR}/model",
    "ARSENAL_VOICE_CACHE": VOICE_CACHE,
    "ARSENAL_VOICE_PROFILES": f"v1={PROFILES}/v1.pt;v2={PROFILES}/v2.pt",
    "ARSENAL_MAX_BATCH": "224",
    "ARSENAL_MAX_ROWS": "224",
    "ARSENAL_MAX_QUEUE": "256",
    "ARSENAL_MAX_FRAMES": "192",
    "ARSENAL_BATCH_WINDOW_MS": "150",
    "ARSENAL_BATCH_TARGET": "224",
    "ARSENAL_PREWARM": "1",
    "ARSENAL_PREWARM_B": "192",
    "ARSENAL_TIMELINE": "1",
    "ARSENAL_DEBUG": "1",
}


@dev.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    timeout=1200,
)
def build_assets() -> str:
    """Build voice cache and profiles into the persistent Volume. Idempotent."""
    import os
    import subprocess

    os.chdir("/root/arsenal")
    os.makedirs(PROFILES, exist_ok=True)
    os.makedirs(VOICE_CACHE, exist_ok=True)
    out: list[str] = []

    if not os.path.exists(f"{PROFILES}/v1.pt"):
        subprocess.run(
            [
                "python",
                "Code/batch/build_voice_profiles.py",
                PROFILES,
                "v1=Code/probes/ref/voice.wav",
                "v2=Code/probes/ref/voice.wav",
            ],
            cwd="/root/arsenal",
            check=True,
        )
        out.append("profiles built")
    else:
        out.append("profiles present")

    if not os.path.exists(f"{VOICE_CACHE}/d4084099c4e63fd8.pt"):
        env = dict(os.environ)
        env["ARSENAL_VOICE_CACHE"] = VOICE_CACHE
        subprocess.run(
            ["python", "Code/batch/build_voice_cache.py"],
            cwd="/root/arsenal",
            env=env,
            check=True,
        )
        out.append("voice cache built")
    else:
        out.append("voice cache present")

    cache.commit()
    return "; ".join(out)


@dev.function(image=image, timeout=1800, cpu=4, memory=8192)
def probe(
    bursts: int = 2,
    per_burst: int = 224,
    single_profile: str = "v1",
    limits: int = 256,
    out: str = "/tmp/probe.json",
) -> int:
    """Co-located load prober. Runs in the same Modal region as serve."""
    import os
    import subprocess

    e = dict(os.environ)
    e.update(
        {
            "ARSENAL_LOAD_BASE": "https://tushar-ps2--arsenal-tts-t4-serve.us-east.modal.run",
            "ARSENAL_LOAD_BURSTS": str(bursts),
            "ARSENAL_LOAD_PER_BURST": str(per_burst),
            "ARSENAL_LOAD_LIMITS": str(limits),
            "ARSENAL_LOAD_OUT": out,
        }
    )
    if single_profile == "none":
        e.pop("ARSENAL_LOAD_SINGLE_PROFILE", None)
        e["ARSENAL_LOAD_PROFILES"] = "0"
    else:
        e["ARSENAL_LOAD_SINGLE_PROFILE"] = single_profile
    result = subprocess.run(
        ["python", "Code/probes/probe_http_load.py"], cwd="/root/arsenal", env=e
    )
    if os.path.exists(out):
        print(open(out).read())
    return result.returncode


@dev.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    timeout=1800,
)
def direct_bench(bs: int = 32, bursts: int = 3) -> dict:
    """Direct BatchedStream first-emit test on a Modal T4, no HTTP."""
    import sys
    import time

    import torch

    sys.path.insert(0, CODE_DIR)
    from batch.server import Settings, TTSEngine

    texts = [
        "Hello there.",
        "The quick brown fox jumps over the lazy dog near the river.",
        "This is a longer sentence that has several words and needs more frames to finish.",
        "Namaste, this is a test sentence for the direct bench.",
    ] * ((bs // 4) + 1)
    texts = texts[:bs]

    engine = TTSEngine(Settings())
    engine.load()
    out: dict[str, float] = {}
    for burst in range(bursts):
        first: dict[int, float] = {}

        def cb(row: int, frame, elapsed: float) -> None:
            first.setdefault(int(row), elapsed * 1000.0)

        start = time.perf_counter()
        engine.stream.stream(texts, on_chunk=cb)
        wall = (time.perf_counter() - start) * 1000.0
        vals = sorted(first.values())
        out[f"burst_{burst}_p50_ms"] = round(vals[len(vals) // 2], 2)
        out[f"burst_{burst}_p95_ms"] = round(vals[min(len(vals) - 1, int(len(vals) * 0.95))], 2)
        out[f"burst_{burst}_max_ms"] = round(vals[-1], 2)
        out[f"burst_{burst}_wall_ms"] = round(wall, 2)
        out[f"burst_{burst}_rows"] = len(vals)
    torch.cuda.synchronize()
    print(out)
    return out


@app.function(
    image=image,
    gpu="T4",
    volumes={CACHE_DIR: cache},
    env=common_env,
    cpu=8,
    memory=16384,
    timeout=3600,
    scaledown_window=60,
    min_containers=0,
    max_containers=1,
)
@modal.concurrent(max_inputs=256)
@modal.asgi_app()
def serve():
    import sys

    sys.path.insert(0, CODE_DIR)
    from batch.server import app as fastapi_app

    return fastapi_app
