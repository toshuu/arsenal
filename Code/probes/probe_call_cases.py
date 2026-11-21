"""Fresh-server call-mode case runner. Local GPU or Modal container."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DEFAULT = ROOT / "Code" / "probes" / "out" / "call_cases"
PROFILE_FILE = ROOT / "Code" / "probes" / "out" / "voice_4s_cond.pt"
TEXT = "Hello, can you hear me now?"


def affinity():
    try:
        return sorted(os.sched_getaffinity(0))
    except Exception:
        return list(range(os.cpu_count() or 4))


def cpu_span(cpus):
    if not cpus:
        return None
    return ",".join(str(c) for c in cpus)


def base_env(server_cpus, client_cpus, quiet=3, hard_cap=40, grace=10, first_frames=8):
    env = os.environ.copy()
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES", "0"),
            "ARSENAL_DEBUG": "1",
            "ARSENAL_TIMELINE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "ARSENAL_MAX_QUEUE": "4096",
            "ARSENAL_MAX_ROWS": "640",
            "ARSENAL_MAX_BATCH": "640",
            "ARSENAL_MAX_FRAMES": "192",
            "ARSENAL_BATCH_WINDOW_MS": "150",
            "ARSENAL_BATCH_TARGET": "640",
            "ARSENAL_CALL_FIRST_QUIET_MS": str(quiet),
            "ARSENAL_CALL_FIRST_HARD_CAP_MS": str(hard_cap),
            "ARSENAL_CALL_FIRST_GRACE_MS": str(grace),
            "ARSENAL_CALL_FIRST_MAX_BATCH": "640",
            "ARSENAL_CALL_FIRST_MAX_FRAMES": str(first_frames),
            "ARSENAL_CALL_CONT_MAX_FRAMES": "192",
            "ARSENAL_VOICE_PROFILES": f"v1={PROFILE_FILE}",
            "ARSENAL_PREWARM": "1",
            "ARSENAL_PREWARM_B": "192",
        }
    )
    return env


def taskset(cpus, cmd):
    span = cpu_span(cpus)
    if span:
        return ["taskset", "-c", span] + cmd
    return cmd


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
    raise RuntimeError(f"server not ready: {last}")


def http_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def start_server(env, server_cpus, log_path):
    log = open(log_path, "w")
    cmd = taskset(
        server_cpus,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "batch.server:app",
            "--app-dir",
            "Code",
            "--host",
            "127.0.0.1",
            "--port",
            "8081",
            "--log-level",
            "warning",
            "--no-access-log",
        ],
    )
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc, log


def stop_server(proc, log):
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)
    except Exception:
        proc.kill()
    try:
        log.close()
    except Exception:
        pass
    time.sleep(1.0)


def run_client(env, client_cpus, args, timeout=1800):
    cmd = taskset(
        client_cpus,
        [sys.executable, "Code/probes/call_load_client.py"] + args,
    )
    r = subprocess.run(
        cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout
    )
    return r


def server_summary(metrics, reps):
    m = metrics.get("metrics", {})
    bs = m.get("batch_size", {}) or {}
    count = bs.get("count") or 0
    return {
        "batches_total": count,
        "batches_per_rep": count / reps if reps else None,
        "batch_rows_p50": bs.get("p50"),
        "batch_rows_p95": bs.get("p95"),
        "batch_wait_p95": (m.get("batch_wait_ms", {}) or {}).get("p95"),
        "batch_spread_p95": (m.get("batch_spread_ms", {}) or {}).get("p95"),
        "ws_text_to_submit_p95": (m.get("ws_text_to_submit_ms", {}) or {}).get("p95"),
        "ws_text_to_first_p95": (m.get("ws_text_to_first_byte_ms", {}) or {}).get("p95"),
        "ws_send_to_recv_p95": (m.get("ws_send_to_recv_ms", {}) or {}).get("p95"),
        "timeline_p95": m.get("timeline_p95"),
        "queue_p95": (m.get("queue_ms", {}) or {}).get("p95"),
        "call_first_p95": (m.get("call_first_ms", {}) or {}).get("p95"),
        "call_first_p50": (m.get("call_first_ms", {}) or {}).get("p50"),
        "request_first_p95": (m.get("request_first_chunk_ms", {}) or {}).get("p95"),
        "chunk_p95": (m.get("chunk_ms", {}) or {}).get("p95"),
        "active_call_sessions": m.get("active_call_sessions"),
        "queue_depth": metrics.get("queue_depth"),
        "vram_peak_mb": (m.get("vram_peak_mb", {}) or {}).get("max"),
        "batch_classes": m.get("batch_classes", []),
        "errors_last": m.get("last_errors", []),
    }


def client_summary(out):
    return {
        "mode": out.get("mode"),
        "b": out.get("b"),
        "rate": out.get("rate"),
        "first_p50": (out.get("first_byte", {}) or {}).get("p50"),
        "first_p95": (out.get("first_byte", {}) or {}).get("p95"),
        "first_max": (out.get("first_byte", {}) or {}).get("max"),
        "connect_p50": (out.get("connect", {}) or {}).get("p50"),
        "connect_p95": (out.get("connect", {}) or {}).get("p95"),
        "started_p50": (out.get("started", {}) or {}).get("p50"),
        "started_p95": (out.get("started", {}) or {}).get("p95"),
        "errors": out.get("errors"),
        "elapsed_s": out.get("elapsed_s"),
        "rows": out.get("rows"),
        "rows_per_s": out.get("rows_per_s"),
        "p50_of_p50": out.get("p50_of_p50"),
        "median_p95": out.get("median_p95"),
        "p95_of_p95": out.get("p95_of_p95"),
        "spread_p95": out.get("spread_p95"),
        "runs": out.get("runs"),
    }


def run_case(name, client_args, repeats, out_dir, quiet=3, hard_cap=40, grace=10, first_frames=8):
    cpus = affinity()
    server_cpus = cpus[: max(1, len(cpus) - 1)]
    client_cpus = cpus[-1:]
    env = base_env(server_cpus, client_cpus, quiet, hard_cap, grace, first_frames)
    env["ARSENAL_SERVER_CPUS"] = cpu_span(server_cpus) or ""
    env["ARSENAL_CLIENT_CPUS"] = cpu_span(client_cpus) or ""
    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    log_path = case_dir / "server.log"
    client_out = case_dir / "client.json"
    proc, log = start_server(env, server_cpus, log_path)
    result = {
        "case": name,
        "server_cpus": cpu_span(server_cpus),
        "client_cpus": cpu_span(client_cpus),
        "args": client_args,
    }
    try:
        base = "http://127.0.0.1:8081"
        result["health"] = wait_ready(base)
        try:
            http_json(base + "/debug/reset", timeout=10)
        except Exception:
            pass
        t0 = time.monotonic()
        r = run_client(
            env, client_cpus, client_args + ["--url", base, "--out", str(client_out)]
        )
        result["client_rc"] = r.returncode
        result["client_seconds"] = time.monotonic() - t0
        if r.stderr:
            result["client_stderr"] = r.stderr[-3000:]
        if client_out.exists():
            out = json.loads(client_out.read_text())
            result["client"] = client_summary(out)
        else:
            result["client"] = {"error": "no_client_json"}
        try:
            raw_metrics = http_json(base + "/metrics")
            result["metrics_raw"] = raw_metrics
            result["metrics"] = server_summary(raw_metrics, repeats)
        except Exception as e:
            result["metrics"] = {"error": str(e)}
        try:
            result["drain"] = http_json(base + "/debug/drain?timeout=30&empty_cache=1")
        except Exception as e:
            result["drain"] = {"error": str(e)}
        try:
            result["vram"] = http_json(base + "/debug/vram")
        except Exception as e:
            result["vram"] = {"error": str(e)}
    except Exception as e:
        result["error"] = str(e)
    finally:
        stop_server(proc, log)
    (case_dir / "case.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return result


def run_debug_case(name, path, out_dir, quiet=3, hard_cap=40, grace=10, first_frames=8):
    cpus = affinity()
    server_cpus = cpus[: max(1, len(cpus) - 1)]
    client_cpus = cpus[-1:]
    env = base_env(server_cpus, client_cpus, quiet, hard_cap, grace, first_frames)
    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    log_path = case_dir / "server.log"
    proc, log = start_server(env, server_cpus, log_path)
    result = {"case": name, "path": path, "server_cpus": cpu_span(server_cpus)}
    try:
        base = "http://127.0.0.1:8081"
        result["health"] = wait_ready(base)
        try:
            http_json(base + "/debug/reset", timeout=10)
        except Exception:
            pass
        t0 = time.monotonic()
        result["debug"] = http_json(base + path, timeout=900)
        result["seconds"] = time.monotonic() - t0
        try:
            result["metrics"] = server_summary(http_json(base + "/metrics"), 1)
        except Exception as e:
            result["metrics"] = {"error": str(e)}
        try:
            result["vram"] = http_json(base + "/debug/vram")
        except Exception as e:
            result["vram"] = {"error": str(e)}
    except Exception as e:
        result["error"] = str(e)
    finally:
        stop_server(proc, log)
    (case_dir / "case.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--only", default="")
    ap.add_argument("--burst-bs", default="256,320,384,448")
    ap.add_argument("--poisson-rates", default="256,320,384")
    ap.add_argument("--quiet", type=float, default=3)
    ap.add_argument("--hard-cap", type=float, default=40)
    ap.add_argument("--grace", type=float, default=10)
    ap.add_argument("--first-frames", type=int, default=8)
    ap.add_argument("--warmups", type=int, default=2)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    results = []
    burst_bs = [int(x) for x in args.burst_bs.split(",") if x.strip()]
    poisson_rates = [int(x) for x in args.poisson_rates.split(",") if x.strip()]
    if not only or "burst" in only:
        for b in burst_bs:
            results.append(
                run_case(
                    f"burst_b{b}{args.tag}",
                    [
                        "--mode",
                        "burst",
                        "--b",
                        str(b),
                        "--repeats",
                        str(args.repeats),
                        "--warmups",
                        str(args.warmups),
                        "--max-frames",
                        str(args.first_frames),
                        "--text",
                        TEXT,
                        "--profile",
                        "v1",
                    ],
                    args.repeats + args.warmups,
                    out_dir,
                    args.quiet,
                    args.hard_cap,
                    args.grace,
                    args.first_frames,
                )
            )
    if not only or "poisson" in only:
        for rate in poisson_rates:
            results.append(
                run_case(
                    f"poisson_{rate}{args.tag}",
                    [
                        "--mode",
                        "poisson",
                        "--rate",
                        str(rate),
                        "--duration",
                        "30",
                        "--max-frames",
                        str(args.first_frames),
                        "--text",
                        TEXT,
                        "--profile",
                        "v1",
                    ],
                    1,
                    out_dir,
                    args.quiet,
                    args.hard_cap,
                    args.grace,
                    args.first_frames,
                )
            )
    if not only or "mixed" in only:
        results.append(
            run_debug_case(
                f"mixed_c128_n32{args.tag}",
                f"/debug/callmixed?call=128&normal=32&first_max_frames={args.first_frames}&first_only=1&profile=v1",
                out_dir,
                args.quiet,
                args.hard_cap,
                args.grace,
            )
        )
    if not only or "cancel" in only:
        results.append(
            run_debug_case(
                f"cancel_b128{args.tag}",
                f"/debug/callcancel?b=128&cancel_frac=0.5&first_max_frames={args.first_frames}&profile=v1",
                out_dir,
                args.quiet,
                args.hard_cap,
                args.grace,
            )
        )
    (out_dir / "all_cases.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
