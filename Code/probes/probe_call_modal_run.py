"""In-container Modal call probe: fresh server per case."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/root/arsenal")
OUT = Path("/tmp/call_probe_out")


def wait_ready(base, timeout=300):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                data = json.loads(r.read().decode())
                if data.get("ready"):
                    return data
                last = data
        except Exception as e:
            last = str(e)
        time.sleep(0.5)
    raise RuntimeError(f"not ready: {last}")


def http_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def start_server(env, log_path):
    log = open(log_path, "w")
    cmd = ["taskset", "-c", "0,1,2,3", sys.executable, "-m", "uvicorn",
           "batch.server:app", "--app-dir", "Code", "--host", "127.0.0.1",
           "--port", "8081", "--log-level", "warning", "--no-access-log"]
    p = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    return p, log


def stop_server(p, log):
    try:
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=30)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    try:
        log.close()
    except Exception:
        pass
    time.sleep(1.0)


def run_client(env, args, out):
    cmd = ["taskset", "-c", "4,5,6,7", sys.executable, "Code/probes/call_load_client.py"] + args + ["--out", out]
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=1800)
    return r


def server_summary(metrics, reps):
    m = metrics.get("metrics", {})
    bs = m.get("batch_size", {}) or {}
    count = bs.get("count") or 0
    return {
        "batches_total": count,
        "batches_per_rep": count / reps if reps else None,
        "batch_rows_p50": bs.get("p50"), "batch_rows_p95": bs.get("p95"),
        "queue_p95": (m.get("queue_ms", {}) or {}).get("p95"),
        "call_first_p50": (m.get("call_first_ms", {}) or {}).get("p50"),
        "call_first_p95": (m.get("call_first_ms", {}) or {}).get("p95"),
        "vram_peak_mb": (m.get("vram_peak_mb", {}) or {}).get("max"),
        "errors_last": m.get("last_errors", []),
    }


def client_summary(out):
    return {
        "mode": out.get("mode"), "b": out.get("b"), "rate": out.get("rate"),
        "first_p50": (out.get("first_byte", {}) or {}).get("p50"),
        "first_p95": (out.get("first_byte", {}) or {}).get("p95"),
        "connect_p50": (out.get("connect", {}) or {}).get("p50"),
        "connect_p95": (out.get("connect", {}) or {}).get("p95"),
        "started_p50": (out.get("started", {}) or {}).get("p50"),
        "started_p95": (out.get("started", {}) or {}).get("p95"),
        "errors": out.get("errors"),
        "rows_per_s": out.get("rows_per_s"),
        "p50_of_p50": out.get("p50_of_p50"), "median_p95": out.get("median_p95"),
        "p95_of_p95": out.get("p95_of_p95"), "runs": out.get("runs"),
    }


def run_case(name, client_args, reps, base_env):
    case_dir = OUT / name
    case_dir.mkdir(parents=True, exist_ok=True)
    env = dict(base_env)
    proc, log = start_server(env, case_dir / "server.log")
    result = {"case": name}
    try:
        base = "http://127.0.0.1:8081"
        result["health"] = wait_ready(base)
        try:
            http_json(base + "/debug/reset")
        except Exception:
            pass
        out = str(case_dir / "client.json")
        r = run_client(env, client_args + ["--url", base], out)
        result["client_rc"] = r.returncode
        if r.stderr:
            result["client_stderr"] = r.stderr[-2000:]
        if Path(out).exists():
            result["client"] = client_summary(json.loads(Path(out).read_text()))
        result["metrics"] = server_summary(http_json(base + "/metrics"), reps)
    except Exception as e:
        result["error"] = str(e)
    finally:
        stop_server(proc, log)
    print(json.dumps(result), flush=True)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "CUDA_VISIBLE_DEVICES": "0", "ARSENAL_DEBUG": "1", "ARSENAL_TIMELINE": "1",
        "PYTHONUNBUFFERED": "1", "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        "ARSENAL_MAX_QUEUE": "4096", "ARSENAL_MAX_ROWS": "640", "ARSENAL_MAX_BATCH": "640",
        "ARSENAL_MAX_FRAMES": "192", "ARSENAL_BATCH_WINDOW_MS": "150", "ARSENAL_BATCH_TARGET": "640",
        "ARSENAL_CALL_FIRST_QUIET_MS": "50", "ARSENAL_CALL_FIRST_HARD_CAP_MS": "300",
        "ARSENAL_CALL_FIRST_GRACE_MS": "20", "ARSENAL_CALL_FIRST_MAX_BATCH": "640",
        "ARSENAL_CALL_FIRST_MAX_FRAMES": "8", "ARSENAL_CALL_CONT_MAX_FRAMES": "192",
        "ARSENAL_PREWARM": "1", "ARSENAL_PREWARM_B": "192",
    })
    cases = {}
    for b in [256, 320, 384, 448]:
        cases[f"burst_b{b}"] = run_case(
            f"burst_b{b}",
            ["--mode", "burst", "--b", str(b), "--repeats", "10", "--warmups", "4",
             "--max-frames", "8", "--text", "Hello, can you hear me now?", "--profile", "v1"],
            14, env)
    for rate in [256, 320, 384]:
        cases[f"poisson_{rate}"] = run_case(
            f"poisson_{rate}",
            ["--mode", "poisson", "--rate", str(rate), "--duration", "30",
             "--max-frames", "8", "--text", "Hello, can you hear me now?", "--profile", "v1"],
            1, env)
    # mixed
    case_dir = OUT / "mixed_c128_n32"
    case_dir.mkdir(parents=True, exist_ok=True)
    proc, log = start_server(env, case_dir / "server.log")
    try:
        base = "http://127.0.0.1:8081"
        wait_ready(base)
        http_json(base + "/debug/reset")
        t0 = time.monotonic()
        data = http_json(base + "/debug/callmixed?call=128&normal=32&first_max_frames=8&first_only=1&profile=v1", timeout=900)
        cases["mixed_c128_n32"] = {"debug": data, "seconds": time.monotonic()-t0,
            "metrics": server_summary(http_json(base+"/metrics"), 1)}
    except Exception as e:
        cases["mixed_c128_n32"] = {"error": str(e)}
    finally:
        stop_server(proc, log)
    (OUT / "all_results.json").write_text(json.dumps(cases, indent=2))
    print("DONE", flush=True)
    return cases


if __name__ == "__main__":
    main()
