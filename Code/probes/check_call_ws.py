"""Check the call-mode WebSocket path without a GPU."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from batch.server import Settings, create_app


class FakeStream:
    def _fits_frame_budget(self, text):
        return True

    def _text_chunks(self, text):
        return [text]


class FakeEngine:
    ready = True

    def has_profile(self, profile_id):
        return profile_id == "v1"

    def _stream_for(self, profile_id):
        return FakeStream()

    def chunks_for(self, text, profile_id=None):
        return [text]

    def batch_key(self, text, profile_id=None):
        return len(text.split())

    def synthesize(
        self,
        texts,
        max_frames=None,
        stop=None,
        profile_id=None,
        profile_ids=None,
        on_chunk=None,
        on_stage=None,
    ):
        if on_chunk is not None:
            for row, _ in enumerate(texts):
                on_chunk(row, np.zeros(2400, dtype=np.float32), 0.0)
        return [np.zeros(2400, dtype=np.float32) for _ in texts]


def main() -> int:
    result = {}
    os.environ["ARSENAL_DEBUG"] = "1"
    settings = Settings(max_batch=8, max_queue=8, timeout_s=5)
    app = create_app(engine=FakeEngine(), settings=settings, start_engine=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/tts") as ws:
        ws.send_json({"type": "start"})
        result["started"] = ws.receive_json() == {"event": "started"}

        ws.send_json({"type": "text", "text": "Hello there."})
        started = ws.receive_json()
        result["chunk_start"] = (
            started.get("event") == "chunk_start" and started.get("index") == 0
        )
        audio = ws.receive_bytes()
        result["pcm"] = len(audio) > 0
        done = ws.receive_json()
        result["chunk_done"] = done.get("event") == "chunk_done" and done.get("samples", 0) > 0

        ws.send_json({"type": "cancel"})
        result["cancelled"] = ws.receive_json() == {"event": "cancelled"}

    with client.websocket_connect("/ws/tts") as ws:
        ws.send_json({"type": "start"})
        ws.receive_json()
        ws.send_json({"type": "text", "text": "Hello there."})
        ws.receive_json()
        ws.receive_bytes()
        ws.receive_json()
        ws.send_json({"type": "flush"})
        result["flushed"] = ws.receive_json() == {"event": "flushed"}
    result["flush_closed"] = True

    response = client.post(
        "/tts/stream?mode=call", json={"text": "Hello there.", "max_frames": 32}
    )
    result["call_stream"] = response.status_code == 200 and len(response.content) > 0

    debug_urls = {
        "callramp": "/debug/callramp?b=4&repeats=1&first_max_frames=32",
        "callmixed": "/debug/callmixed?call=2&normal=2&first_max_frames=32",
        "callcancel": "/debug/callcancel?b=4&cancel_frac=0.5&first_max_frames=32",
    }
    for name, url in debug_urls.items():
        reply = client.get(url)
        result[name] = reply.status_code == 200 and bool(reply.json().get("ok"))

    meta = client.get("/metrics").json()["metrics"]
    result["sessions_closed"] = meta["active_call_sessions"] == 0
    result["call_first_ms"] = meta["call_first_ms"]["count"] >= 1
    result["ok"] = bool(
        result["started"]
        and result["chunk_start"]
        and result["pcm"]
        and result["chunk_done"]
        and result["cancelled"]
        and result["flushed"]
        and result["flush_closed"]
        and result["call_stream"]
        and result["callramp"]
        and result["callmixed"]
        and result["callcancel"]
        and result["sessions_closed"]
        and result["call_first_ms"]
        and meta["first_chunk_ms_by_class"]["call_first"]["count"] >= 1
        and "call_first_wait_behind_normal_ms" in meta
    )
    out = Path(__file__).resolve().parent / "out" / "check_call_ws.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
