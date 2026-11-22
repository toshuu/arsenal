"""Phase 4 formation probe: find a call_first policy that keeps one batch."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("ARSENAL_DEBUG", "1")
os.environ.setdefault("ARSENAL_POCKET_TTS", "/kaggle/working/pocket-tts")
os.environ.setdefault("ARSENAL_MODEL_DIR", str(ROOT / "Code/model"))
os.environ.setdefault("ARSENAL_VOICE", "/kaggle/working/refHD.wav")
os.environ.setdefault("ARSENAL_PREWARM", "0")
CAP = 640
for key, value in {
    "ARSENAL_MAX_QUEUE": "4096",
    "ARSENAL_MAX_ROWS": str(CAP),
    "ARSENAL_MAX_BATCH": str(CAP),
    "ARSENAL_CALL_FIRST_MAX_BATCH": str(CAP),
    "ARSENAL_CALL_FIRST_SUB_BATCH": str(CAP),
}.items():
    os.environ.setdefault(key, value)

sys.path.insert(0, str(ROOT / "Code"))
from fastapi.testclient import TestClient
from batch.server import create_app

TEXT = "Hello, can you hear me clearly right now?"
OUT = ROOT / "Code/probes/out/phase4_formation"
POLICIES = [
    {"name": "default", "window": 150, "quiet": 0, "hard": 0},
    {"name": "q2h20", "window": 150, "quiet": 2, "hard": 20},
    {"name": "q2h30", "window": 150, "quiet": 2, "hard": 30},
    {"name": "q3h40", "window": 150, "quiet": 3, "hard": 40},
]
BS = [224, 320, 448]
MODES = ["sentence", "utterance"]
CALLS = 3


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = create_app()
    rows = []
    with TestClient(app) as client:
        for _ in range(300):
            if client.get("/health").json().get("ready"):
                break
            time.sleep(1)
        else:
            raise SystemExit("server not ready")
        metrics = app.state.metrics
        worker = app.state.worker
        for policy in POLICIES:
            os.environ["ARSENAL_BATCH_WINDOW_MS"] = str(policy["window"])
            os.environ["ARSENAL_CALL_FIRST_QUIET_MS"] = str(policy["quiet"])
            os.environ["ARSENAL_CALL_FIRST_HARD_CAP_MS"] = str(policy["hard"])
            worker.reload_config()
            for mode in MODES:
                for b in BS:
                    for call in range(CALLS):
                        before = len(metrics.batch_size)
                        url = (
                            "/debug/callramp?b=%d&repeats=1&first_only=1"
                            "&stream_mode=%s&first_max_frames=8&text=%s"
                            % (b, mode, TEXT.replace(" ", "%20"))
                        )
                        response = client.get(url)
                        response.raise_for_status()
                        run = response.json()["runs"][0]
                        first = run.get("first_byte_ms") or {}
                        row = {
                            "policy": policy["name"],
                            "window": policy["window"],
                            "quiet": policy["quiet"],
                            "hard": policy["hard"],
                            "mode": mode,
                            "b": b,
                            "call": call,
                            "warm": call > 0,
                            "p50": first.get("p50"),
                            "p95": first.get("p95"),
                            "errors": run.get("errors"),
                            "batch_sizes": run.get("batch_sizes"),
                        }
                        rows.append(row)
                        print(json.dumps(row), flush=True)
                        data = {"ok": True, "cap": CAP, "policies": POLICIES, "rows": rows}
                        (OUT / "formation.json").write_text(json.dumps(data, indent=2))
    data = {"ok": True, "cap": CAP, "policies": POLICIES, "rows": rows}
    (OUT / "formation.json").write_text(json.dumps(data, indent=2))
    print(json.dumps({"ok": True, "rows": len(rows)}))


if __name__ == "__main__":
    main()
