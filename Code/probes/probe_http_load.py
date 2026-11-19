"""HTTP load probe: mixed profiles and text lengths on one T4."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "probes" / "out" / "probe_http_load.json"
PORT = 8081
BASE = f"http://127.0.0.1:{PORT}"
BURSTS = int(os.getenv("ARSENAL_LOAD_BURSTS", "5"))
PER_BURST = int(os.getenv("ARSENAL_LOAD_PER_BURST", "32"))
TEXTS = [
    "Hello there.",
    "The quick brown fox jumps over the lazy dog near the river.",
    "This is a longer sentence that has several words and needs more frames to finish.",
    "नमस्ते, यह एक परीक्षण वाक्य है। This is a mixed language test for the load probe.",
]
PROFILES = ["v1", "v2", None] if os.getenv("ARSENAL_LOAD_PROFILES", "1") == "1" else [None]
LOAD_LIMITS = int(os.getenv("ARSENAL_LOAD_LIMITS", "0"))
WARMUP = os.getenv("ARSENAL_LOAD_WARMUP", "1") == "1"
SINGLE_PROFILE = os.getenv("ARSENAL_LOAD_SINGLE_PROFILE") or None


def build_profiles() -> dict[str, str]:
    profile_dir = Path("/tmp/arsenal_load_profiles")
    profile_dir.mkdir(exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "Code" / "batch" / "build_voice_profiles.py"),
        str(profile_dir),
        "v1=Code/probes/ref/voice.wav",
        "v2=Code/probes/ref/voice.wav",
    ]
    env = dict(os.environ)
    if os.getenv("ARSENAL_POCKET_TTS"):
        env["PYTHONPATH"] = os.environ["ARSENAL_POCKET_TTS"] + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(cmd, cwd=ROOT, env=env, check=True, capture_output=True, timeout=300)
    return {"v1": str(profile_dir / "v1.pt"), "v2": str(profile_dir / "v2.pt")}


def start_server(profiles: dict[str, str]) -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    env["ARSENAL_VOICE_PROFILES"] = ";".join(f"{k}={v}" for k, v in profiles.items())
    if os.getenv("ARSENAL_POCKET_TTS"):
        env["ARSENAL_POCKET_TTS"] = os.environ["ARSENAL_POCKET_TTS"]
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "batch.server:app",
        "--app-dir",
        str(ROOT / "Code"),
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ]
    loop = os.getenv("ARSENAL_UVICORN_LOOP")
    http = os.getenv("ARSENAL_UVICORN_HTTP")
    backlog = os.getenv("ARSENAL_UVICORN_BACKLOG")
    if loop:
        cmd += ["--loop", loop]
    if http:
        cmd += ["--http", http]
    if backlog:
        cmd += ["--backlog", backlog]
    if os.getenv("ARSENAL_UVICORN_ACCESS_LOG", "1") == "0":
        cmd.append("--no-access-log")
    server_cores = os.getenv("ARSENAL_SERVER_CORES")
    if server_cores:
        cmd = ["taskset", "-c", server_cores] + cmd
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with httpx.Client(base_url=BASE, timeout=5) as client:
        for _ in range(120):
            try:
                if client.get("/health").status_code == 200:
                    return proc
            except Exception:
                pass
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("server did not become ready")


async def one_request(
    client: httpx.AsyncClient, index: int, start_at: float
) -> dict[str, object]:
    text = TEXTS[index % len(TEXTS)]
    profile = SINGLE_PROFILE or PROFILES[index % len(PROFILES)]
    body: dict[str, object] = {"text": text}
    if profile:
        body["voice_profile"] = profile
    await asyncio.sleep(max(0.0, start_at - time.perf_counter()))
    start = time.perf_counter()
    first_ms = None
    header_ms = None
    audio_bytes = 0
    status = 0
    error = None
    try:
        async with client.stream("POST", "/tts/stream", json=body, timeout=120) as response:
            status = response.status_code
            header_ms = (time.perf_counter() - start) * 1000
            async for chunk in response.aiter_bytes():
                if first_ms is None:
                    first_ms = (time.perf_counter() - start) * 1000
                audio_bytes += len(chunk)
    except Exception as exc:
        status = 0
        error = repr(exc)
    return {
        "status": status,
        "error": error,
        "header_ms": header_ms,
        "first_ms": first_ms,
        "audio_s": audio_bytes / 2 / 24000,
        "total_ms": (time.perf_counter() - start) * 1000,
    }


async def run_bursts(client: httpx.AsyncClient, result: dict[str, object]) -> list[dict[str, object]]:
    if WARMUP:
        await asyncio.gather(*(client.get("/health") for _ in range(PER_BURST)))
        result["warmup"] = PER_BURST
    rows: list[dict[str, object]] = []
    for burst in range(BURSTS):
        start = time.perf_counter()
        start_at = time.perf_counter() + 0.05
        batch = await asyncio.gather(
            *(
                one_request(client, burst * PER_BURST + index, start_at)
                for index in range(PER_BURST)
            )
        )
        wall = time.perf_counter() - start
        rows.extend(batch)
        audio_s = sum(float(r["audio_s"]) for r in batch)
        result[f"burst_{burst}_wall_s"] = round(wall, 3)
        result[f"burst_{burst}_rtf"] = round(wall / audio_s, 3) if audio_s else 0
        result[f"burst_{burst}_ok"] = all(r["status"] == 200 for r in batch)
    return rows


def main() -> int:
    profiles = build_profiles()
    proc = start_server(profiles)
    result: dict[str, object] = {
        "bursts": BURSTS,
        "per_burst": PER_BURST,
        "load_limits": LOAD_LIMITS or "default",
        "warmup": WARMUP,
        "single_profile": SINGLE_PROFILE,
        "server_cores": os.getenv("ARSENAL_SERVER_CORES"),
        "uvicorn": {
            "loop": os.getenv("ARSENAL_UVICORN_LOOP"),
            "http": os.getenv("ARSENAL_UVICORN_HTTP"),
            "backlog": os.getenv("ARSENAL_UVICORN_BACKLOG"),
            "access_log": os.getenv("ARSENAL_UVICORN_ACCESS_LOG", "1"),
        },
    }
    client_kwargs: dict[str, object] = {"base_url": BASE, "timeout": 60}
    if LOAD_LIMITS > 0:
        client_kwargs["limits"] = httpx.Limits(
            max_connections=LOAD_LIMITS, max_keepalive_connections=LOAD_LIMITS
        )

    async def run() -> tuple[list[dict[str, object]], dict[str, object]]:
        async with httpx.AsyncClient(**client_kwargs) as client:
            rows = await run_bursts(client, result)
            metrics = (await client.get("/metrics")).json()["metrics"]
        return rows, metrics

    try:
        rows, metrics = asyncio.run(run())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    firsts = sorted(float(r["first_ms"]) for r in rows if r["first_ms"] is not None)
    headers = sorted(float(r["header_ms"]) for r in rows if r["header_ms"] is not None)
    result["requests"] = len(rows)
    result["header_p50_ms"] = round(statistics.median(headers), 2) if headers else 0
    result["header_p95_ms"] = (
        round(headers[min(len(headers) - 1, int(len(headers) * 0.95))], 2)
        if headers
        else 0
    )
    result["status_200"] = sum(r["status"] == 200 for r in rows)
    result["errors"] = len(rows) - result["status_200"]
    result["error_values"] = [r["error"] for r in rows if r.get("error")]
    result["first_p50_ms"] = round(statistics.median(firsts), 2) if firsts else 0
    result["first_p95_ms"] = (
        round(firsts[min(len(firsts) - 1, int(len(firsts) * 0.95))], 2) if firsts else 0
    )
    result["first_max_ms"] = round(max(firsts), 2) if firsts else 0
    result["first_values_ms"] = [round(v, 1) for v in firsts]
    result["server_metrics"] = metrics
    result["ok"] = bool(
        result["errors"] == 0
        and result["first_p95_ms"] <= 350
        and all(result[f"burst_{i}_rtf"] < 1.0 for i in range(BURSTS))
        and all(result[f"burst_{i}_ok"] for i in range(BURSTS))
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "requests": result["requests"], "p95": result["first_p95_ms"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
