"""Phase 4 quiet fix probe at B=320."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
PORT = int(os.getenv("ARSENAL_PHASE4_QUIET_FIX_PORT", "8130"))
TEXT = "Hello, can you hear me clearly right now?"
OUT = ROOT / "Code/probes/out/phase4_quiet_fix"
CAP = 640
POLICIES = [
    {"name": "q2h30_nb", "env": {"ARSENAL_BATCH_TARGET": "640", "ARSENAL_CALL_FIRST_QUIET_MS": "2", "ARSENAL_CALL_FIRST_HARD_CAP_MS": "30", "ARSENAL_CALL_FIRST_BUCKETS": "0", "ARSENAL_CALL_FIRST_MIN_EARLY": "32"}},
    {"name": "q3h40_nb", "env": {"ARSENAL_BATCH_TARGET": "640", "ARSENAL_CALL_FIRST_QUIET_MS": "3", "ARSENAL_CALL_FIRST_HARD_CAP_MS": "40", "ARSENAL_CALL_FIRST_BUCKETS": "0", "ARSENAL_CALL_FIRST_MIN_EARLY": "32"}},
]


def base_env():
    env = os.environ.copy()
    env.update({
        "ARSENAL_PREWARM": "0",
        "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
        "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
        "ARSENAL_VOICE": str(REF),
        "ARSENAL_DEBUG": "1",
        "ARSENAL_MAX_QUEUE": "4096",
        "ARSENAL_MAX_ROWS": str(CAP),
        "ARSENAL_MAX_BATCH": str(CAP),
        "ARSENAL_CALL_FIRST_MAX_BATCH": str(CAP),
        "ARSENAL_CALL_FIRST_SUB_BATCH": str(CAP),
        "ARSENAL_BATCH_WINDOW_MS": "150",
    })
    return env


def wait(base, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        try:
            response = requests.get(base + "/health", timeout=2)
            if response.ok and response.json().get("ready"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("server not ready")


def run_policy(policy, calls, port):
    env = base_env()
    env.update(policy["env"])
    OUT.mkdir(parents=True, exist_ok=True)
    log = (OUT / ("server_%s.log" % policy["name"])).open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "batch.server:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT)
    rows = []
    try:
        base = "http://127.0.0.1:%d" % port
        wait(base)
        for mode in ["sentence", "utterance"]:
            for call in range(calls):
                params = {"b": 320, "repeats": 1, "first_only": 1, "stream_mode": mode, "first_max_frames": 8, "text": TEXT}
                response = requests.get(base + "/debug/callramp", params=params, timeout=600)
                response.raise_for_status()
                run = response.json()["runs"][0]
                first = run.get("first_byte_ms") or {}
                row = {"policy": policy["name"], "mode": mode, "call": call, "warm": call > 1,
                       "p50": first.get("p50"), "p95": first.get("p95"), "errors": run.get("errors"),
                       "batch_sizes": run.get("batch_sizes"), "vram_after": (run.get("vram_mb") or {}).get("after")}
                rows.append(row)
                print(json.dumps(row), flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        log.close()
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUT / "fix.json")
    args = parser.parse_args()
    args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for index, policy in enumerate(POLICIES):
        rows = run_policy(policy, args.calls, PORT + index)
        all_rows.extend(rows)
        args.out.write_text(json.dumps({"ok": True, "policies": POLICIES, "rows": all_rows}, indent=2))
    args.out.write_text(json.dumps({"ok": True, "policies": POLICIES, "rows": all_rows}, indent=2))
    print(json.dumps({"ok": True, "rows": len(all_rows)}))


if __name__ == "__main__":
    main()
