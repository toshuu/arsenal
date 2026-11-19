"""Ramp HTTP load across B values and optional window sweep."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "probes" / "out"
PROBE_JSON = OUT / "probe_http_load.json"


def run_one(b: int, window: int | None, label: str) -> dict:
    env = dict(os.environ)
    env["ARSENAL_POCKET_TTS"] = env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts")
    env["PYTHONPATH"] = env["ARSENAL_POCKET_TTS"] + os.pathsep + env.get("PYTHONPATH", "")
    env["ARSENAL_LOAD_LIMITS"] = str(max(256, b))
    env["ARSENAL_LOAD_SINGLE_PROFILE"] = "v1"
    env["ARSENAL_MAX_BATCH"] = str(b)
    env["ARSENAL_MAX_ROWS"] = str(b)
    env["ARSENAL_BATCH_TARGET"] = str(b)
    env["ARSENAL_LOAD_BURSTS"] = "2"
    env["ARSENAL_LOAD_PER_BURST"] = str(b)
    env["ARSENAL_SERVER_CORES"] = env.get("ARSENAL_SERVER_CORES", "0,1")
    env["ARSENAL_UVICORN_LOOP"] = env.get("ARSENAL_UVICORN_LOOP", "uvloop")
    env["ARSENAL_UVICORN_HTTP"] = env.get("ARSENAL_UVICORN_HTTP", "httptools")
    env["ARSENAL_UVICORN_BACKLOG"] = env.get("ARSENAL_UVICORN_BACKLOG", "1024")
    env["ARSENAL_UVICORN_ACCESS_LOG"] = "0"
    if window is not None:
        env["ARSENAL_BATCH_WINDOW_MS"] = str(window)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-u", "Code/probes/probe_http_load.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    wall_run = time.perf_counter() - t0
    try:
        d = json.loads(PROBE_JSON.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    sm = d.get("server_metrics") or {}
    sr = sm.get("request_first_chunk_ms") or {}
    sq = sm.get("queue_ms") or {}
    rtfs = [d.get(f"burst_{i}_rtf") for i in range(int(d.get("bursts") or 0))]
    rtfs = [r for r in rtfs if r is not None]
    row = {
        "label": label,
        "b": b,
        "window_ms": window if window is not None else int(os.getenv("ARSENAL_BATCH_WINDOW_MS", "150")),
        "server_p50": sr.get("p50"),
        "server_p95": sr.get("p95"),
        "queue_p95": sq.get("p95"),
        "client_p50": d.get("first_p50_ms"),
        "client_p95": d.get("first_p95_ms"),
        "errors": d.get("errors"),
        "requests": d.get("requests"),
        "ok": d.get("ok"),
        "rtf_max": max(rtfs) if rtfs else None,
        "wall_s": round(wall_run, 2),
        "stdout": (proc.stdout or "").strip()[-200:],
        "stderr_tail": (proc.stderr or "").strip()[-300:],
        "returncode": proc.returncode,
    }
    return row


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "ramp"
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    if mode == "ramp":
        bs = [48, 64, 96, 128, 160, 192, 224]
        window = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        out_path = OUT / f"ramp_step1_w{window}.json"
        for b in bs:
            print(f"RUN b={b} window={window}", flush=True)
            row = run_one(b, window, f"ramp_b{b}_w{window}")
            rows.append(row)
            out_path.write_text(json.dumps({"mode": mode, "window": window, "rows": rows}, indent=2), encoding="utf-8")
            print(json.dumps({"b": b, "server_p95": row["server_p95"], "client_p95": row["client_p95"], "errors": row["errors"], "ok": row["ok"]}), flush=True)
            sp = row.get("server_p95")
            if row.get("errors") or (sp is not None and sp > 350):
                print(f"STOP at b={b}", flush=True)
                break
    elif mode == "sweep":
        b = int(sys.argv[2])
        windows = [int(x) for x in sys.argv[3].split(",")]
        out_path = OUT / f"sweep_b{b}.json"
        for w in windows:
            print(f"RUN b={b} window={w}", flush=True)
            row = run_one(b, w, f"sweep_b{b}_w{w}")
            rows.append(row)
            out_path.write_text(json.dumps({"mode": mode, "b": b, "rows": rows}, indent=2), encoding="utf-8")
            print(json.dumps({"w": w, "server_p95": row["server_p95"], "client_p95": row["client_p95"], "errors": row["errors"]}), flush=True)
    else:
        print("usage: ramp [window] | sweep B w1,w2,...")
        return 2
    print(json.dumps({"out": str(out_path), "count": len(rows)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
