"""Check sentence and utterance on the real WS server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import requests
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Code" / "probes" / "out" / "ws_quality"
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
PORT = int(os.getenv("ARSENAL_WS_QUALITY_PORT", "8109"))
TEXT = (
    "Life doesn't always go the way we plan, but sometimes the unexpected "
    "moments turn out to be the most beautiful ones. Since there are many "
    "people in this planet which really wants to do good things for you, so "
    "always enjoy and rejoice this life. Because you never know what "
    "wonderful things are waiting for you to discover."
)


def write_wav(path: Path, samples: np.ndarray, sr: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


def wait_ready(base: str, timeout_s: float = 240.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=2)
            if r.status_code == 200 and r.json().get("ready"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("server not ready")


def run_mode(base: str, mode: str) -> dict:
    pcm = bytearray()
    events = []
    first_byte_ms = None
    t0 = time.perf_counter()
    with connect(f"ws://127.0.0.1:{PORT}/ws/tts", open_timeout=30, close_timeout=30) as ws:
        ws.send(json.dumps({"type": "start", "stream_mode": mode}))
        events.append(json.loads(ws.recv()))
        ws.send(json.dumps({"type": "text", "text": TEXT}))
        while True:
            msg = ws.recv()
            if isinstance(msg, bytes):
                if first_byte_ms is None:
                    first_byte_ms = (time.perf_counter() - t0) * 1000.0
                pcm.extend(msg)
            else:
                event = json.loads(msg)
                events.append(event)
                if event.get("event") == "utterance_done":
                    break
        ws.send(json.dumps({"type": "flush"}))
        try:
            events.append(json.loads(ws.recv()))
        except Exception:
            pass
    samples = np.frombuffer(bytes(pcm), dtype="<i2").astype(np.float32) / 32768.0
    path = OUT / f"{mode}.wav"
    write_wav(path, samples)
    utter = [e for e in events if e.get("event") == "utterance_done"]
    chunks = utter[0].get("chunks", []) if utter else []
    return {
        "mode": mode,
        "first_byte_ms": round(first_byte_ms or 0.0, 2),
        "audio_sec": round(samples.size / 24000.0, 3),
        "chunks": len(chunks),
        "cap_hits": sum(1 for c in chunks if c.get("cap_hit")),
        "wav": str(path),
        "events": [e.get("event") for e in events],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("ARSENAL_PREWARM", "0")
    env.setdefault("ARSENAL_MODEL_DIR", str(ROOT / "Code" / "model"))
    env.setdefault("ARSENAL_VOICE", str(REF))
    env.setdefault("ARSENAL_CALL_STREAM_MODE", "sentence")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "batch.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]
    log_path = OUT / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_ready(f"http://127.0.0.1:{PORT}")
            rows = [run_mode(f"http://127.0.0.1:{PORT}", m) for m in ("sentence", "utterance")]
            out = {"ok": True, "rows": rows}
            (OUT / "ws_quality.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(out))
            return 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
