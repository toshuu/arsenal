"""HTTP load probe: mixed profiles and text lengths on one T4."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
    proc = subprocess.Popen(
        [
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
        ],
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


def one_request(client: httpx.Client, index: int) -> dict[str, object]:
    text = TEXTS[index % len(TEXTS)]
    profile = PROFILES[index % len(PROFILES)]
    body: dict[str, object] = {"text": text}
    if profile:
        body["voice_profile"] = profile
    start = time.perf_counter()
    first_ms = None
    audio_bytes = 0
    status = 0
    with client.stream("POST", "/tts/stream", json=body, timeout=120) as response:
        status = response.status_code
        for chunk in response.iter_bytes():
            if first_ms is None:
                first_ms = (time.perf_counter() - start) * 1000
            audio_bytes += len(chunk)
    return {
        "status": status,
        "first_ms": first_ms,
        "audio_s": audio_bytes / 2 / 24000,
        "total_ms": (time.perf_counter() - start) * 1000,
    }


def main() -> int:
    profiles = build_profiles()
    proc = start_server(profiles)
    result: dict[str, object] = {"bursts": BURSTS, "per_burst": PER_BURST}
    rows: list[dict[str, object]] = []
    try:
        with httpx.Client(base_url=BASE, timeout=60, limits=httpx.Limits(max_connections=256, max_keepalive_connections=256)) as client:
            for burst in range(BURSTS):
                start = time.perf_counter()
                with ThreadPoolExecutor(max_workers=PER_BURST) as pool:
                    batch = list(
                        pool.map(
                            lambda i: one_request(client, burst * PER_BURST + i),
                            range(PER_BURST),
                        )
                    )
                wall = time.perf_counter() - start
                rows.extend(batch)
                audio_s = sum(float(r["audio_s"]) for r in batch)
                result[f"burst_{burst}_wall_s"] = round(wall, 3)
                result[f"burst_{burst}_rtf"] = round(wall / audio_s, 3) if audio_s else 0
                result[f"burst_{burst}_ok"] = all(r["status"] == 200 for r in batch)
            metrics = client.get("/metrics").json()["metrics"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    firsts = sorted(float(r["first_ms"]) for r in rows if r["first_ms"] is not None)
    result["requests"] = len(rows)
    result["status_200"] = sum(r["status"] == 200 for r in rows)
    result["errors"] = len(rows) - result["status_200"]
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
