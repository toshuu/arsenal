"""Check a long text through the HTTP path with a conditioned profile."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.getenv("ARSENAL_POCKET_TTS"):
    sys.path.insert(0, os.environ["ARSENAL_POCKET_TTS"])
os.chdir(ROOT / "model")
logging.disable(logging.CRITICAL)

from fastapi.testclient import TestClient

from batch.server import Settings, TTSEngine, create_app

OUT = ROOT / "probes" / "out" / "check_long_text_http.json"
TEXT = (
    "The quick brown fox jumps over the lazy dog near the river. "
    "A silver train leaves the station at noon every single day. "
    "Please close the windows before the storm arrives. "
    "The small boat moves slowly under the old stone bridge."
)


def main() -> int:
    result: dict[str, object] = {"text": TEXT}
    settings = Settings(
        max_batch=4,
        max_queue=8,
        max_rows=8,
        max_frames=192,
        timeout_s=180.0,
        max_texts=8,
        max_chars=4000,
    )
    engine = TTSEngine(settings)
    engine.load()
    profile = Path(tempfile.gettempdir()) / "arsenal_probe_profile.pt"
    engine.stream.save_voice_profile(profile, conditioned=True)
    engine.profiles["probe"] = str(profile)
    result["profile_bytes"] = profile.stat().st_size
    result["chunks"] = len(engine.stream._text_chunks(TEXT))

    app = create_app(engine=engine, settings=settings, start_engine=False)
    with TestClient(app) as client:
        health = client.get("/health")
        result["health_status"] = health.status_code

        start = time.perf_counter()
        full = client.post(
            "/tts", json={"text": TEXT, "voice_profile": "probe"}
        )
        result["full_s"] = round(time.perf_counter() - start, 3)
        result["full_status"] = full.status_code
        result["full_type"] = full.headers.get("content-type", "")
        result["full_bytes"] = len(full.content)

        start = time.perf_counter()
        stream = client.post(
            "/tts/stream", json={"text": TEXT, "voice_profile": "probe"}
        )
        result["stream_s"] = round(time.perf_counter() - start, 3)
        result["stream_status"] = stream.status_code
        result["stream_type"] = stream.headers.get("content-type", "")
        result["stream_bytes"] = len(stream.content)

        metrics = client.get("/metrics").json()["metrics"]
        result["first_chunk_count"] = metrics["first_chunk_ms"]["count"]
        result["first_chunk_p95"] = metrics["first_chunk_ms"]["p95"]

    result["profile_loaded"] = "probe" in engine.profile_streams
    result["default_not_conditioned"] = engine.stream.voice_state is None
    result["ok"] = bool(
        result["health_status"] == 200
        and result["full_status"] == 200
        and result["full_type"].startswith("audio/wav")
        and result["full_bytes"] > 100000
        and result["stream_status"] == 200
        and result["stream_type"].startswith("audio/L16")
        and result["stream_bytes"] > 100000
        and result["first_chunk_count"] >= 2
        and result["profile_loaded"]
        and result["default_not_conditioned"]
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "chunks": result["chunks"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
