"""Phase 4 admission probe: cap 640, B=224/320/448, sentence and utterance."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
REF = Path(os.getenv("ARSENAL_PROBE_VOICE", "/kaggle/working/refHD.wav"))
PORT = int(os.getenv("ARSENAL_PHASE4_PORT", "8123"))
TEXT = "Hello, can you hear me clearly right now?"
OUT = ROOT / "Code/probes/out/phase4_admission"


def wait(base, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = requests.get(base + "/health", timeout=2)
            if r.ok and r.json().get("ready"):
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("server not ready")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=640)
    ap.add_argument("--reps", type=int, default=4)
    ap.add_argument("--out", type=Path, default=OUT / "admission.json")
    args = ap.parse_args()
    args.out = args.out if args.out.is_absolute() else (ROOT / args.out).resolve()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        "ARSENAL_PREWARM": "0",
        "ARSENAL_MODEL_DIR": str(ROOT / "Code/model"),
        "ARSENAL_VOICE": str(REF),
        "ARSENAL_DEBUG": "1",
        "ARSENAL_MAX_QUEUE": "4096",
        "ARSENAL_MAX_ROWS": str(args.cap),
        "ARSENAL_MAX_BATCH": str(args.cap),
        "ARSENAL_BATCH_TARGET": str(args.cap),
        "ARSENAL_CALL_FIRST_MAX_BATCH": str(args.cap),
    })
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
                for rep in range(args.reps):
                    params = {
                        "b": b, "repeats": 1, "first_only": 1,
                        "stream_mode": mode, "first_max_frames": 8,
                        "window": 5, "text": TEXT,
                    }
                    r = requests.get(base + "/debug/callramp", params=params, timeout=600)
                    r.raise_for_status()
                    run = r.json()["runs"][0]
                    fb = run.get("first_byte_ms") or {}
                    row = {
                        "mode": mode, "b": b, "rep": rep, "warm": rep > 0,
                        "p50": fb.get("p50"), "p95": fb.get("p95"),
                        "errors": run.get("errors"),
                        "batch_sizes": run.get("batch_sizes"),
                        "vram_after": (run.get("vram_mb") or {}).get("after"),
                    }
                    rows.append(row)
                    print(json.dumps(row), flush=True)
                    args.out.write_text(json.dumps({"ok": True, "cap": args.cap, "rows": rows}, indent=2))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        log.close()
    args.out.write_text(json.dumps({"ok": True, "cap": args.cap, "rows": rows}, indent=2))
    print(json.dumps({"ok": True, "out": str(args.out), "rows": len(rows)}))


if __name__ == "__main__":
    main()
