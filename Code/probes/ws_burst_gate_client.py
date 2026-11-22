"""Burst client for the WS gate. One pre-connected set. No cancel. No drain."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import websockets


def pstats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "p50": None, "p95": None, "max": None, "min": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50": statistics.median(ordered),
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max": max(ordered),
        "min": min(ordered),
    }


async def open_call(url: str, profile: str | None, timeout_s: float, mode: str = "sentence") -> dict:
    t0 = time.perf_counter()
    ws = None
    try:
        ws = await websockets.connect(url, max_size=2**24, open_timeout=timeout_s)
        await ws.send(json.dumps({"type": "start", "voice": profile, "stream_mode": mode}))
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout_s))
        if message.get("event") != "started":
            await ws.close()
            return {"error": "start:%s" % message}
        return {"ws": ws, "connect_ms": (time.perf_counter() - t0) * 1000.0}
    except Exception as exc:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        return {"error": str(exc)}


async def one_call(connection: dict, text: str, timeout_s: float, max_frames: int) -> dict:
    ws = connection["ws"]
    t_send = time.perf_counter()
    first = None
    try:
        await ws.send(json.dumps({
            "type": "text",
            "text": text,
            "max_frames": max_frames,
            "first_only": True,
            "sent_ns": time.time_ns(),
        }))
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout_s)
            if isinstance(message, (bytes, bytearray)):
                if first is None:
                    first = time.perf_counter()
                continue
            event = json.loads(message)
            name = event.get("event")
            if name == "chunk_done":
                break
            if name == "error":
                return {"error": event.get("detail")}
        if first is None:
            return {"error": "no_audio"}
        return {"send_to_first_byte_ms": (first - t_send) * 1000.0}
    except Exception as exc:
        return {"error": str(exc)}


async def burst(live: list[dict], text: str, timeout_s: float, max_frames: int) -> dict:
    barrier = asyncio.Event()

    async def task(connection: dict) -> dict:
        await barrier.wait()
        return await one_call(connection, text, timeout_s, max_frames)

    tasks = [asyncio.create_task(task(connection)) for connection in live]
    barrier.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    values = []
    errors = 0
    for result in results:
        if (
            isinstance(result, BaseException)
            or not isinstance(result, dict)
            or result.get("error")
            or result.get("send_to_first_byte_ms") is None
        ):
            errors += 1
            continue
        values.append(result["send_to_first_byte_ms"])
    return {"first_byte": pstats(values), "errors": errors}


async def run(args) -> dict:
    raw = args.url.rstrip("/")
    if raw.startswith("https://"):
        url = "wss://" + raw[len("https://"):]
    elif raw.startswith("http://"):
        url = "ws://" + raw[len("http://"):]
    elif raw.startswith("ws://") or raw.startswith("wss://"):
        url = raw
    else:
        url = "ws://" + raw
    if not url.endswith("/ws/tts"):
        url = url + "/ws/tts"
    connections = await asyncio.gather(
        *[open_call(url, args.profile, args.timeout, args.mode) for _ in range(args.b)]
    )
    live = [item for item in connections if item.get("ws") is not None]
    connect_fail = len(connections) - len(live)
    runs = []
    try:
        for index in range(args.warmups + args.repeats):
            result = await burst(live, args.text, args.timeout, args.max_frames)
            result["warmup"] = index < args.warmups
            result["rep"] = index
            runs.append(result)
    finally:
        for item in live:
            try:
                await asyncio.wait_for(item["ws"].close(), timeout=5.0)
            except Exception:
                pass
    warm = [item for item in runs if not item["warmup"]]
    p50s = [item["first_byte"]["p50"] for item in warm if item["first_byte"]["p50"] is not None]
    p95s = [item["first_byte"]["p95"] for item in warm if item["first_byte"]["p95"] is not None]
    return {
        "b": args.b,
        "runs": runs,
        "warm_runs": warm,
        "p50_of_p50": statistics.median(p50s) if p50s else None,
        "median_p95": statistics.median(p95s) if p95s else None,
        "p95_of_p95": max(p95s) if p95s else None,
        "errors": sum(item["errors"] for item in runs) + connect_fail,
        "connect_fail": connect_fail,
        "rows": args.b * (args.warmups + args.repeats),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--b", type=int, default=224)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--text", default="Hello, can you hear me clearly right now?")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--mode", default="sentence")
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = asyncio.run(run(args))
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"b": args.b, "p95": out["p95_of_p95"], "errors": out["errors"]}))


if __name__ == "__main__":
    main()
