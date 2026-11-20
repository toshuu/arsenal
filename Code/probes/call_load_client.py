"""Separate-process call-mode load generator (WebSocket /ws/tts)."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import websockets


def pstats(vals):
    if not vals:
        return {"count": 0, "p50": None, "p95": None, "max": None, "min": None}
    s = sorted(vals)
    return {
        "count": len(s),
        "p50": statistics.median(s),
        "p95": s[min(len(s) - 1, int(len(s) * 0.95))],
        "max": max(s),
        "min": min(s),
    }


async def one_call(url, text, max_frames, profile, first_only=True, timeout_s=120):
    t0 = time.perf_counter()
    t_connect = t_started = t_first = None
    err = None
    try:
        async with websockets.connect(url, max_size=2**24, open_timeout=timeout_s) as ws:
            t_connect = time.perf_counter()
            await ws.send(json.dumps({"type": "start", "voice": profile}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout_s))
            if msg.get("event") != "started":
                return {"error": f"start:{msg}"}
            t_started = time.perf_counter()
            await ws.send(json.dumps({"type": "text", "text": text, "max_frames": max_frames}))
            done_chunks = 0
            started_chunks = 0
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout_s)
                if isinstance(msg, (bytes, bytearray)):
                    if t_first is None:
                        t_first = time.perf_counter()
                    if first_only and started_chunks >= 1:
                        try:
                            await ws.send(json.dumps({"type": "cancel"}))
                        except Exception:
                            pass
                        break
                    continue
                ev = json.loads(msg)
                if ev.get("event") == "chunk_start":
                    started_chunks += 1
                elif ev.get("event") == "chunk_done":
                    done_chunks += 1
                    if first_only and done_chunks >= 1:
                        try:
                            await ws.send(json.dumps({"type": "cancel"}))
                        except Exception:
                            pass
                        break
                    if not first_only and started_chunks > 0 and done_chunks == started_chunks:
                        await ws.send(json.dumps({"type": "flush"}))
                elif ev.get("event") == "flushed":
                    break
                elif ev.get("event") == "error":
                    err = ev.get("detail")
                    break
    except Exception as e:
        err = str(e)
    if t_first is None and err is None:
        err = "no_audio"
    out = {}
    if t_connect is not None:
        out["connect_ms"] = (t_connect - t0) * 1000.0
    if t_started is not None:
        out["started_ms"] = (t_started - t0) * 1000.0
    if t_first is not None:
        out["first_byte_ms"] = (t_first - t0) * 1000.0
    if err:
        out["error"] = err
    return out


async def run_burst(url, b, repeats, warmups, text, max_frames, profile, first_only):
    runs = []
    for i in range(warmups + repeats):
        tasks = [asyncio.create_task(one_call(url, text, max_frames, profile, first_only)) for _ in range(b)]
        res = await asyncio.gather(*tasks, return_exceptions=True)
        vals = {"connect_ms": [], "started_ms": [], "first_byte_ms": []}
        errs = 0
        for r in res:
            if isinstance(r, Exception):
                errs += 1
                continue
            if not isinstance(r, dict) or r.get("error") or r.get("first_byte_ms") is None:
                errs += 1
                continue
            for k in vals:
                if r.get(k) is not None:
                    vals[k].append(r[k])
        if i >= warmups:
            runs.append({
                "repeat": i - warmups,
                "connect": pstats(vals["connect_ms"]),
                "started": pstats(vals["started_ms"]),
                "first_byte": pstats(vals["first_byte_ms"]),
                "errors": errs,
                "n": b,
            })
        await asyncio.sleep(0.2)
    def med(key):
        xs = [r["first_byte"][key] for r in runs if r["first_byte"].get(key) is not None]
        return statistics.median(xs) if xs else None
    p95s = [r["first_byte"]["p95"] for r in runs if r["first_byte"].get("p95") is not None]
    return {
        "mode": "burst",
        "b": b,
        "repeats": repeats,
        "warmups": warmups,
        "runs": runs,
        "p50_of_p50": med("p50"),
        "median_p95": med("p95"),
        "p95_of_p95": max(p95s) if p95s else None,
        "spread_p95": (max(p95s) - min(p95s)) if p95s else None,
        "errors": sum(r["errors"] for r in runs),
    }


async def run_poisson(url, rate, duration_s, text, max_frames, profile, first_only):
    tasks = []
    stop = time.monotonic() + duration_s
    next_t = time.monotonic()
    t0 = time.monotonic()
    while next_t < stop:
        now = time.monotonic()
        if now < next_t:
            await asyncio.sleep(next_t - now)
        tasks.append(asyncio.create_task(one_call(url, text, max_frames, profile, first_only)))
        next_t += random.expovariate(rate)
    res = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.monotonic() - t0
    vals = {"connect_ms": [], "started_ms": [], "first_byte_ms": []}
    errs = 0
    for r in res:
        if isinstance(r, Exception):
            errs += 1
            continue
        if not isinstance(r, dict) or r.get("error") or r.get("first_byte_ms") is None:
            errs += 1
            continue
        for k in vals:
            if r.get(k) is not None:
                vals[k].append(r[k])
    return {
        "mode": "poisson",
        "rate": rate,
        "duration_s": duration_s,
        "count": len(tasks),
        "elapsed_s": elapsed,
        "connect": pstats(vals["connect_ms"]),
        "started": pstats(vals["started_ms"]),
        "first_byte": pstats(vals["first_byte_ms"]),
        "errors": errs,
        "rows_per_s": len(vals["first_byte_ms"]) / elapsed if elapsed > 0 else 0,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--mode", choices=["burst", "poisson"], required=True)
    ap.add_argument("--b", type=int, default=256)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--warmups", type=int, default=2)
    ap.add_argument("--rate", type=int, default=256)
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--text", default="Hello, can you hear me now?")
    ap.add_argument("--max-frames", type=int, default=8)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    url = args.url.rstrip("/")
    if url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    elif url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    if not url.endswith("/ws/tts"):
        url = url + "/ws/tts"
    first_only = not args.full
    if args.mode == "burst":
        out = await run_burst(url, args.b, args.repeats, args.warmups, args.text, args.max_frames, args.profile, first_only)
    else:
        out = await run_poisson(url, args.rate, args.duration, args.text, args.max_frames, args.profile, first_only)
    out["url"] = args.url
    out["text"] = args.text
    out["max_frames"] = args.max_frames
    out["first_only"] = first_only
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
