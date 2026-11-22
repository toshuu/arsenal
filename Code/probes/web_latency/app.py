"""Web demo for latency mode. Serves a page and proxies the WS audio path."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent
BACKEND = os.getenv("ARSENAL_DEMO_BACKEND", "ws://127.0.0.1:8169/ws/tts")

app = FastAPI()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-store"})


@app.websocket("/ws/tts")
async def proxy(ws: WebSocket) -> None:
    await ws.accept()
    try:
        async with websockets.connect(BACKEND, max_size=2**24) as backend:
            async def from_browser() -> None:
                while True:
                    message = await ws.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    text = message.get("text")
                    data = message.get("bytes")
                    if text is not None:
                        await backend.send(text)
                    elif data is not None:
                        await backend.send(data)

            async def from_backend() -> None:
                while True:
                    message = await backend.recv()
                    if isinstance(message, str):
                        await ws.send_text(message)
                    else:
                        await ws.send_bytes(message)

            await asyncio.gather(from_browser(), from_backend())
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await ws.send_json({"event": "error", "detail": str(exc)})
        except Exception:
            pass
