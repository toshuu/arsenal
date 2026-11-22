"""Real WebSocket low-latency gate: confirmed quiet formation, max B."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Code/probes/out/ws_burst_gate"
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
PORT = int(os.getenv("ARSENAL_WS_GATE_PORT", "8140"))
TEXT = "Hello, can you hear me clearly right now?"
BATCHES = [224, 320, 384]
MODE = "sentence"
CAP = 640
FIRST_FRAMES = 8


def wait_ready(base: str, timeout_s: float = 300.0) -> None:
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            response = requests.get(base + "/health", timeout=2)
            if response.ok and response.json().get("ready"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("server not ready")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "ARSENAL_PREWARM": "1",
        "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
        "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
        "ARSENAL_VOICE": str(REF),
        "ARSENAL_DEBUG": "1",
        "ARSENAL_MAX_QUEUE": "4096",
        "ARSENAL_MAX_ROWS": str(CAP),
        "ARSENAL_MAX_BATCH": str(CAP),
        "ARSENAL_BATCH_TARGET": str(CAP),
        "ARSENAL_MAX_FRAMES": "192",
        "ARSENAL_BATCH_WINDOW_MS": "150",
        "ARSENAL_CALL_STREAM_MODE": MODE,
        "ARSENAL_CALL_FIRST_MAX_BATCH": str(CAP),
        "ARSENAL_CALL_FIRST_SUB_BATCH": str(CAP),
        "ARSENAL_CALL_FIRST_MAX_FRAMES": str(FIRST_FRAMES),
        "ARSENAL_CALL_CONT_MAX_FRAMES": "192",
        "ARSENAL_CALL_FIRST_QUIET_MS": "50",
        "ARSENAL_CALL_FIRST_HARD_CAP_MS": "300",
        "ARSENAL_CALL_FIRST_GRACE_MS": "20",
    })
    base = "http://127.0.0.1:%d" % PORT
    log = (OUT / "server.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "batch.server:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    rows = []
    try:
        wait_ready(base)
        for batch in BATCHES:
            path = OUT / ("burst_%d.json" % batch)
            requests.get(base + "/debug/reset", timeout=10)
            command = [
                sys.executable, str(ROOT / "Code/probes/ws_burst_gate_client.py"),
                "--url", base, "--b", str(batch),
                "--repeats", "4", "--warmups", "2",
                "--mode", MODE, "--max-frames", str(FIRST_FRAMES),
                "--text", TEXT, "--out", str(path),
            ]
            subprocess.run(
                command, cwd=str(ROOT), check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            server = requests.get(base + "/metrics", timeout=10).json()
            metrics = server.get("metrics", {})
            rows.append({
                "mode": MODE,
                "b": batch,
                "p50_of_p50": data.get("p50_of_p50"),
                "median_p95": data.get("median_p95"),
                "p95_of_p95": data.get("p95_of_p95"),
                "errors": data.get("errors"),
                "connect_fail": data.get("connect_fail"),
                "call_first_ms": metrics.get("call_first_ms"),
                "call_first_wait_ms": metrics.get("call_first_wait_ms"),
                "batch_wait_ms": metrics.get("batch_wait_ms"),
                "batch_size": metrics.get("batch_size"),
                "runs": data.get("runs", []),
            })
            time.sleep(1.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        log.close()

    def passes(row: dict) -> bool:
        return bool(
            row["errors"] == 0
            and row["p95_of_p95"] is not None
            and row["p95_of_p95"] <= 350.0
        )

    passing = [row["b"] for row in rows if passes(row)]
    max_b = max(passing) if passing else None
    gate_224 = passes(next(row for row in rows if row["b"] == 224))
    gate_320 = passes(next(row for row in rows if row["b"] == 320))
    out = {
        "ok": True,
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "client_sha256": hashlib.sha256((ROOT / "Code/probes/ws_burst_gate_client.py").read_bytes()).hexdigest(),
        "gate_224": gate_224,
        "gate_320": gate_320,
        "max_b_under_350": max_b,
        "mode": MODE,
        "cap": CAP,
        "first_frames": FIRST_FRAMES,
        "text": TEXT,
        "batches": BATCHES,
        "rows": rows,
    }
    (OUT / "gate.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    summary = {
        "gate_320": gate_320,
        "max_b_under_350": max_b,
        "p95": {str(row["b"]): row["p95_of_p95"] for row in rows},
        "errors": sum(int(row["errors"] or 0) for row in rows),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
