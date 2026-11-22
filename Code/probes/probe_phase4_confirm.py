"""Phase 4 confirmation probe: default window, cap 640, real uvicorn server."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
PORT = int(os.getenv("ARSENAL_PHASE4_CONFIRM_PORT", "8125"))
TEXT = "Hello, can you hear me clearly right now?"
OUT = ROOT / "Code/probes/out/phase4_confirm"


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=int, default=640)
    parser.add_argument("--calls", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUT / "confirm.json")
    args = parser.parse_args()
    args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        "ARSENAL_PREWARM": "0",
        "ARSENAL_POCKET_TTS": env.get("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts"),
        "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
        "ARSENAL_VOICE": str(REF),
        "ARSENAL_DEBUG": "1",
        "ARSENAL_MAX_QUEUE": "4096",
        "ARSENAL_MAX_ROWS": str(args.cap),
        "ARSENAL_MAX_BATCH": str(args.cap),
        "ARSENAL_CALL_FIRST_MAX_BATCH": str(args.cap),
        "ARSENAL_CALL_FIRST_SUB_BATCH": str(args.cap),
        "ARSENAL_CALL_FIRST_QUIET_MS": "0",
        "ARSENAL_CALL_FIRST_HARD_CAP_MS": "0",
    })
    env.pop("ARSENAL_BATCH_WINDOW_MS", None)
    log = (args.out.parent / "server.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "batch.server:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT / "Code"), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    rows = []
    try:
        base = "http://127.0.0.1:%d" % PORT
        wait(base)
        for mode in ["sentence", "utterance"]:
            for b in [224, 320, 448]:
                for call in range(args.calls):
                    params = {
                        "b": b, "repeats": 1, "first_only": 1,
                        "stream_mode": mode, "first_max_frames": 8,
                        "text": TEXT,
                    }
                    response = requests.get(
                        base + "/debug/callramp", params=params, timeout=600
                    )
                    response.raise_for_status()
                    run = response.json()["runs"][0]
                    first = run.get("first_byte_ms") or {}
                    row = {
                        "mode": mode, "b": b, "call": call, "warm": call > 1,
                        "p50": first.get("p50"), "p95": first.get("p95"),
                        "errors": run.get("errors"),
                        "batch_sizes": run.get("batch_sizes"),
                        "vram_after": (run.get("vram_mb") or {}).get("after"),
                    }
                    rows.append(row)
                    print(json.dumps(row), flush=True)
                    data = {"ok": True, "cap": args.cap, "rows": rows}
                    args.out.write_text(json.dumps(data, indent=2))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        log.close()
    data = {"ok": True, "cap": args.cap, "rows": rows}
    args.out.write_text(json.dumps(data, indent=2))
    print(json.dumps({"ok": True, "out": str(args.out), "rows": len(rows)}))


if __name__ == "__main__":
    main()
