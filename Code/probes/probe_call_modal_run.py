"""In-container Modal call probe: server + separate-process load client."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path


def wait_ready(base, timeout=300):
    import urllib.request
    for _ in range(timeout):
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                data = json.loads(r.read().decode())
                if data.get("ready"):
                    return data
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("server not ready")


def run_client(args, out):
    cmd = ["taskset", "-c", "4,5,6,7", "python", "Code/probes/call_load_client.py"] + args + ["--out", out]
    r = subprocess.run(cmd, cwd="/root/arsenal", capture_output=True, text=True, timeout=1800)
    print("CLIENT_RC", r.returncode)
    if r.stdout:
        print(r.stdout[-4000:])
    if r.stderr:
        print("STDERR", r.stderr[-2000:])
    if Path(out).exists():
        return json.loads(Path(out).read_text())
    return {"error": "no_output", "rc": r.returncode, "stderr": r.stderr[-500:]}


def main():
    out_dir = Path("/tmp/call_probe_out")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "CUDA_VISIBLE_DEVICES": "0",
        "ARSENAL_DEBUG": "1",
        "ARSENAL_MODEL_DIR": env.get("ARSENAL_MODEL_DIR", "/root/arsenal/Code/model"),
        "ARSENAL_MAX_QUEUE": "4096",
        "ARSENAL_MAX_ROWS": "640",
        "ARSENAL_MAX_BATCH": "640",
        "ARSENAL_BATCH_TARGET": "640",
        "ARSENAL_CALL_FIRST_QUIET_MS": "3",
        "ARSENAL_CALL_FIRST_HARD_CAP_MS": "40",
        "ARSENAL_CALL_FIRST_GRACE_MS": "10",
        "ARSENAL_CALL_FIRST_MAX_BATCH": "640",
        "ARSENAL_CALL_FIRST_MAX_FRAMES": "8",
    })
    server_cmd = ["taskset", "-c", "0,1,2,3", "python", "-m", "uvicorn", "batch.server:app",
                  "--app-dir", "Code", "--host", "127.0.0.1", "--port", "8081",
                  "--log-level", "warning", "--no-access-log"]
    server = subprocess.Popen(server_cmd, cwd="/root/arsenal", env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        base = "http://127.0.0.1:8081"
        wait_ready(base)
        print("READY")
        import urllib.request
        results = {}

        def reset_metrics():
            try:
                req = urllib.request.Request(base + "/metrics/reset", method="POST")
                urllib.request.urlopen(req, timeout=10).read()
            except Exception:
                pass

        def get_metrics():
            try:
                with urllib.request.urlopen(base + "/metrics", timeout=10) as r:
                    return json.loads(r.read().decode())
            except Exception as e:
                return {"error": str(e)}

        # debug callramp (in-server formation/batching diagnostic)
        for b in [256, 320, 384]:
            reset_metrics()
            try:
                url = (base + f"/debug/callramp?b={b}&repeats=5&warmups=2&first_max_frames=8"
                       "&cont_max_frames=16&first_only=1&text=Hello%2C+can+you+hear+me+now%3F")
                with urllib.request.urlopen(url, timeout=900) as r:
                    results[f"callramp_{b}"] = json.loads(r.read().decode())
            except Exception as e:
                results[f"callramp_{b}"] = {"error": str(e)}
            results[f"callramp_{b}_metrics"] = get_metrics()

        # ws burst via separate-process client (pinned to 4-7)
        for b in [256, 320, 384]:
            out = str(out_dir / f"ws_burst_b{b}_mf8.json")
            reset_metrics()
            results[f"ws_burst_{b}"] = run_client([
                "--url", base, "--mode", "burst", "--b", str(b),
                "--repeats", "5", "--warmups", "2", "--max-frames", "8",
                "--text", "Hello, can you hear me now?",
            ], out)
            results[f"ws_burst_{b}_metrics"] = get_metrics()

        Path(out_dir / "all_results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
    finally:
        server.send_signal(signal.SIGTERM)
        try:
            server.wait(timeout=20)
        except Exception:
            server.kill()


if __name__ == "__main__":
    main()
