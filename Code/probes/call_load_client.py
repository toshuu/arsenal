"""Separate-process call-mode load generator (WebSocket /ws/tts)."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
import urllib.request
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


def http_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def metrics_snapshot(base):
    try:
        return http_json(base + "/metrics", timeout=10)
    except Exception as e:
        return {"error": str(e)}


def drained(base):
    snap = metrics_snapshot(base)
    m = snap.get("metrics", {})
    return (
        snap.get("queue_depth", 0) == 0
        and m.get("active_call_sessions", 0) == 0
        and not snap.get("error")
    )


async def drain(base, timeout_s=120.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await asyncio.to_thread(drained, base):
            try:
                await asyncio.to_thread(
                    http_json, base + "/debug/drain?timeout=5&empty_cache=1", 10
                )
            except Exception:
                pass
            await asyncio.sleep(0.2)
            return True
        await asyncio.sleep(0.02)
    return False


async def open_call(url, profile, timeout_s):
    t0 = time.perf_counter()
    out = {"t0": t0}
    try:
        ws = await websockets.connect(url, max_size=2**24, open_timeout=timeout_s)
        out["connect_ms"] = (time.perf_counter() - t0) * 1000.0
        await ws.send(json.dumps({"type": "start", "voice": profile}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout_s))
        if msg.get("event") != "started":
            await ws.close()
            out["error"] = f"start:{msg}"
            return out
        out["started_ms"] = (time.perf_counter() - t0) * 1000.0
        out["ws"] = ws
    except Exception as e:
        out["error"] = str(e)
    return out


async def stream_first(ws, text, max_frames, first_only, timeout_s):
    t_send = time.perf_counter()
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "text",
                    "text": text,
                    "max_frames": max_frames,
                    "first_only": first_only,
                    "sent_ns": time.time_ns(),
                }
            )
        )
        t_first = None
        done = 0
        err = None
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout_s)
            if isinstance(msg, (bytes, bytearray)):
                if t_first is None:
                    t_first = time.perf_counter()
                if not first_only:
                    continue
                continue
            ev = json.loads(msg)
            name = ev.get("event")
            if name == "chunk_start":
                continue
            if name == "chunk_done":
                done += 1
                if first_only:
                    break
                continue
            if name == "flushed":
                break
            if name == "error":
                err = ev.get("detail")
                break
        if first_only:
            try:
                await ws.send(json.dumps({"type": "cancel"}))
            except Exception:
                pass
        if t_first is None and err is None:
            err = "no_audio"
        out = {"send_to_first_byte_ms": None, "done": done}
        if t_first is not None:
            out["send_to_first_byte_ms"] = (t_first - t_send) * 1000.0
            out["first_byte_at_ms"] = (t_first - t_send) * 1000.0
        if err:
            out["error"] = err
        return out
    except Exception as e:
        return {"send_to_first_byte_ms": None, "error": str(e)}


async def close_all(conns):
    for c in conns:
        ws = c.get("ws")
        if ws is None:
            continue
        try:
            await ws.close()
        except Exception:
            pass


async def burst_rep(live, text, max_frames, profile, first_only, timeout_s):
    barrier = asyncio.Event()

    async def one(c):
        await barrier.wait()
        r = await stream_first(c["ws"], text, max_frames, first_only, timeout_s)
        r["connect_ms"] = c.get("connect_ms")
        r["started_ms"] = c.get("started_ms")
        return r

    tasks = [asyncio.create_task(one(c)) for c in live]
    barrier.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    errors = 0
    for r in results:
        if isinstance(r, BaseException) or not isinstance(r, dict):
            errors += 1
            continue
        if r.get("error") or r.get("send_to_first_byte_ms") is None:
            errors += 1
            continue
        items.append(r)
    firsts = [r["send_to_first_byte_ms"] for r in items]
    connects = [r["connect_ms"] for r in items if r.get("connect_ms") is not None]
    startups = [r["started_ms"] for r in items if r.get("started_ms") is not None]
    slow = sorted(items, key=lambda r: r["send_to_first_byte_ms"], reverse=True)[:5]
    return {
        "first_byte": pstats(firsts),
        "connect": pstats(connects),
        "started": pstats(startups),
        "errors": errors,
        "n": len(live),
        "slowest": [
            {
                "send_to_first_byte_ms": round(r["send_to_first_byte_ms"], 2),
                "connect_ms": round(r["connect_ms"], 2) if r.get("connect_ms") else None,
                "started_ms": round(r["started_ms"], 2) if r.get("started_ms") else None,
            }
            for r in slow
        ],
    }


def batch_run_metrics(before, after):
    am = after.get("metrics", {})
    classes = am.get("batch_classes", [])
    return {
        "batch_size_after": am.get("batch_size"),
        "batch_wait_ms_after": am.get("batch_wait_ms"),
        "batch_spread_ms_after": am.get("batch_spread_ms"),
        "chunk_ms_after": am.get("chunk_ms"),
        "queue_ms_after": am.get("queue_ms"),
        "call_first_ms_after": am.get("call_first_ms"),
        "active_call_sessions": am.get("active_call_sessions"),
        "queue_depth": after.get("queue_depth"),
        "batch_classes": classes,
        "batch_sizes": am.get("batch_size", {}).get("max"),
    }


async def run_burst(base, url, b, repeats, warmups, text, max_frames, profile, first_only, timeout_s):
    runs = []
    t_start = time.perf_counter()
    conns = await asyncio.gather(
        *[open_call(url, profile, timeout_s) for _ in range(b)]
    )
    live = [c for c in conns if c.get("ws") is not None]
    connect_fail = len(conns) - len(live)
    connects_all = [c["connect_ms"] for c in live if c.get("connect_ms") is not None]
    starts_all = [c["started_ms"] for c in live if c.get("started_ms") is not None]
    try:
        for i in range(warmups + repeats):
            before = await asyncio.to_thread(metrics_snapshot, base)
            await drain(base)
            r = await burst_rep(live, text, max_frames, profile, first_only, timeout_s)
            r["errors"] += connect_fail
            drained_ok = await drain(base)
            after = await asyncio.to_thread(metrics_snapshot, base)
            if i >= warmups:
                r["repeat"] = i - warmups
                r["drained_after"] = drained_ok
                r["server"] = batch_run_metrics(before, after)
                runs.append(r)
    finally:
        await close_all(conns)
    p95s = [r["first_byte"]["p95"] for r in runs if r["first_byte"].get("p95") is not None]
    p50s = [r["first_byte"]["p50"] for r in runs if r["first_byte"].get("p50") is not None]
    return {
        "mode": "burst",
        "connect": pstats(connects_all),
        "started": pstats(starts_all),
        "b": b,
        "repeats": repeats,
        "warmups": warmups,
        "runs": runs,
        "p50_of_p50": statistics.median(p50s) if p50s else None,
        "median_p95": statistics.median(p95s) if p95s else None,
        "p95_of_p95": max(p95s) if p95s else None,
        "spread_p95": (max(p95s) - min(p95s)) if p95s else None,
        "errors": sum(r["errors"] for r in runs),
        "connect_fail": connect_fail,
        "elapsed_s": time.perf_counter() - t_start,
        "rows": b * (warmups + repeats),
    }


async def poisson_one(url, text, max_frames, profile, first_only, timeout_s):
    c = await open_call(url, profile, timeout_s)
    if c.get("ws") is None:
        return {"error": c.get("error", "connect"), "connect_ms": c.get("connect_ms")}
    try:
        r = await stream_first(c["ws"], text, max_frames, first_only, timeout_s)
        r["connect_ms"] = c.get("connect_ms")
        r["started_ms"] = c.get("started_ms")
        return r
    finally:
        await close_all([c])


async def run_poisson(base, url, rate, duration_s, text, max_frames, profile, first_only, timeout_s):
    await drain(base)
    before = await asyncio.to_thread(metrics_snapshot, base)
    tasks = []
    stop = time.monotonic() + duration_s
    next_t = time.monotonic()
    t0 = time.monotonic()
    while next_t < stop:
        now = time.monotonic()
        if now < next_t:
            await asyncio.sleep(next_t - now)
        tasks.append(
            asyncio.create_task(
                poisson_one(url, text, max_frames, profile, first_only, timeout_s)
            )
        )
        next_t += random.expovariate(rate)
    res = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.monotonic() - t0
    drained_ok = await drain(base)
    after = await asyncio.to_thread(metrics_snapshot, base)
    vals = []
    connects = []
    startups = []
    errs = 0
    for r in res:
        if isinstance(r, BaseException) or not isinstance(r, dict):
            errs += 1
            continue
        if r.get("error") or r.get("send_to_first_byte_ms") is None:
            errs += 1
            continue
        vals.append(r["send_to_first_byte_ms"])
        if r.get("connect_ms") is not None:
            connects.append(r["connect_ms"])
        if r.get("started_ms") is not None:
            startups.append(r["started_ms"])
    return {
        "mode": "poisson",
        "rate": rate,
        "duration_s": duration_s,
        "count": len(tasks),
        "elapsed_s": elapsed,
        "first_byte": pstats(vals),
        "connect": pstats(connects),
        "started": pstats(startups),
        "errors": errs,
        "rows_per_s": len(vals) / elapsed if elapsed > 0 else 0,
        "drained_after": drained_ok,
        "server": batch_run_metrics(before, after),
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
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = args.url.rstrip("/")
    if raw.startswith("http://"):
        url = "ws://" + raw[len("http://"):]
    elif raw.startswith("https://"):
        url = "wss://" + raw[len("https://"):]
    else:
        url = raw
    base = raw
    if base.startswith("ws://"):
        base = "http://" + base[len("ws://"):]
    elif base.startswith("wss://"):
        base = "https://" + base[len("wss://"):]
    if not url.endswith("/ws/tts"):
        url = url + "/ws/tts"
    first_only = not args.full
    if args.mode == "burst":
        out = await run_burst(
            base, url, args.b, args.repeats, args.warmups, args.text,
            args.max_frames, args.profile, first_only, args.timeout,
        )
    else:
        out = await run_poisson(
            base, url, args.rate, args.duration, args.text,
            args.max_frames, args.profile, first_only, args.timeout,
        )
    out["url"] = args.url
    out["text"] = args.text
    out["max_frames"] = args.max_frames
    out["first_only"] = first_only
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
