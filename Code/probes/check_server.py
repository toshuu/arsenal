"""Check the serving layer without a GPU."""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from batch.server import QueueFull, Settings, create_app


class FakeEngine:
    ready = True
    last_profile = None

    def has_profile(self, profile_id):
        return profile_id == "v1"

    def batch_key(self, text, profile_id=None):
        return len(text.split())

    def synthesize(self, texts, max_frames=None, stop=None, profile_id=None):
        type(self).last_profile = profile_id
        return [np.zeros(2400, dtype=np.float32) for _ in texts]


class BlockingEngine:
    ready = True

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def synthesize(self, texts, max_frames=None, stop=None, profile_id=None):
        self.started.set()
        self.release.wait(5)
        return [np.zeros(2400, dtype=np.float32) for _ in texts]


class SlowEngine:
    ready = True

    def synthesize(self, texts, max_frames=None, stop=None, profile_id=None):
        time.sleep(0.3)
        return [np.zeros(2400, dtype=np.float32) for _ in texts]


def main() -> int:
    result: dict[str, object] = {}
    settings = Settings(max_batch=2, max_queue=2, timeout_s=5)
    app = create_app(engine=FakeEngine(), settings=settings, start_engine=False)
    client = TestClient(app)

    health = client.get("/health")
    result["health_ok"] = health.status_code == 200 and health.json()["ready"] is True

    one = client.post("/tts", json={"text": "Hello there."})
    result["wav_ok"] = (
        one.status_code == 200
        and one.headers["content-type"] == "audio/wav"
        and len(one.content) > 44
    )

    many = client.post("/tts/batch", json={"texts": ["One.", "Two."]})
    body = many.json() if many.status_code == 200 else {}
    decoded = [len(base64.b64decode(item["wav_base64"])) for item in body.get("audio", [])]
    result["batch_ok"] = many.status_code == 200 and len(decoded) == 2 and min(decoded) > 44

    profile = client.post("/tts", json={"text": "Hi.", "voice_profile": "v1"})
    result["profile_ok"] = (
        profile.status_code == 200 and FakeEngine.last_profile == "v1"
    )
    unknown = client.post("/tts", json={"text": "Hi.", "voice_profile": "nope"})
    result["unknown_profile_rejected"] = unknown.status_code == 400
    mixed = client.post(
        "/tts/batch",
        json={"texts": ["one two", "three four five"], "voice_profile": "v1"},
    )
    result["mixed_profile_ok"] = (
        mixed.status_code == 200 and len(mixed.json().get("audio", [])) == 2
    )

    empty = client.post("/tts", json={"text": "   "})
    result["empty_rejected"] = empty.status_code == 422

    long_text = "x" * (settings.max_chars + 1)
    too_long = client.post("/tts", json={"text": long_text})
    result["long_rejected"] = too_long.status_code == 413

    timeout_settings = Settings(max_batch=1, max_queue=2, timeout_s=0.1)
    timeout_app = create_app(engine=SlowEngine(), settings=timeout_settings, start_engine=False)
    timeout_client = TestClient(timeout_app)
    timed = timeout_client.post("/tts", json={"text": "Hello."})
    result["timeout_status"] = timed.status_code

    blocking = BlockingEngine()
    block_settings = Settings(max_batch=1, max_queue=1, timeout_s=5)
    block_app = create_app(engine=blocking, settings=block_settings, start_engine=False)
    worker = block_app.state.worker
    first = worker.submit(["one"], None)
    blocking.started.wait(2)
    second = worker.submit(["two"], None)
    full = False
    try:
        worker.submit(["three"], None)
    except QueueFull:
        full = True
    second.cancelled = True
    blocking.release.set()
    first.future.result(timeout=5)
    cancelled = False
    try:
        second.future.result(timeout=5)
    except BaseException:
        cancelled = True
    result["queue_full_ok"] = full
    result["cancel_ok"] = cancelled

    result["ok"] = bool(
        result["health_ok"]
        and result["wav_ok"]
        and result["batch_ok"]
        and result["empty_rejected"]
        and result["long_rejected"]
        and result["timeout_status"] == 504
        and result["queue_full_ok"]
        and result["cancel_ok"]
    )
    out = Path(__file__).resolve().parent / "out" / "check_server.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
