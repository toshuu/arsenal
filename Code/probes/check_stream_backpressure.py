"""Check that a slow stream reader stops work and does not grow the queue."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import numpy as np

from batch.server import Settings, create_app

OUT = Path(__file__).resolve().parent / "out" / "check_stream_backpressure.json"


class ChunkEngine:
    def chunks_for(self, text, profile_id=None):
        return [text]

    ready = True

    def synthesize(self, texts, max_frames=None, stop=None, profile_id=None, profile_ids=None, on_chunk=None):
        for _ in range(200):
            if stop is not None and stop.is_set():
                break
            if on_chunk is not None:
                on_chunk(0, np.full(2400, 0.1, dtype=np.float32), 0.0)
        return [np.zeros(2400, dtype=np.float32) for _ in texts]


async def run() -> dict[str, object]:
    app = create_app(
        engine=ChunkEngine(),
        settings=Settings(max_batch=1, max_queue=4, timeout_s=10),
        start_engine=False,
    )
    transport = httpx.ASGITransport(app=app)
    chunks = 0
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/tts/stream", json={"text": "Hi."}) as response:
            status = response.status_code
            async for _ in response.aiter_bytes():
                chunks += 1
                await asyncio.sleep(0.01)
    metrics = app.state.metrics.snapshot()
    return {
        "status": status,
        "chunks": chunks,
        "slow_clients": metrics["slow_clients"],
        "queue_depth": app.state.worker.depth,
        "ok": bool(status == 200 and chunks < 200 and metrics["slow_clients"] > 0),
    }


def main() -> int:
    result = asyncio.run(asyncio.wait_for(run(), timeout=20))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
