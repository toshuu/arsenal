"""Measure voice length and first-chunk cap at high batch.

Run: python Code/probes/probe_prefill_levers.py
Writes: Code/probes/out/probe_prefill_levers.json
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "Code" / "probes" / "out"
BENCH = REPO / "Code" / "probes" / "bench_batch_server.py"
COMBOS = [(v, c) for v in (6.5, 4.0, 3.0, 2.0) for c in (50, 24, 16)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    gpu = ""
    for voice_seconds, first_tokens in COMBOS:
        out = OUT / f"lever_v{voice_seconds}_c{first_tokens}.json"
        cmd = [
            sys.executable, str(BENCH),
            "--bs", "96,128", "--max-b", "128", "--bursts", "2", "--warmup", "1",
            "--parity-b", "0", "--fp16",
            "--voice-seconds", str(voice_seconds),
            "--first-tokens", str(first_tokens),
            "--out", str(out),
        ]
        subprocess.run(cmd, check=True, cwd=REPO)
        data = json.loads(out.read_text())
        gpu = data.get("gpu_name") or data.get("device", "")
        for item in data["results"]:
            s = item["summary"]
            rows.append(
                {
                    "voice_seconds": voice_seconds,
                    "first_tokens": first_tokens,
                    "batch": item["batch"],
                    "p50_ms": s["ttfa_p50_ms"],
                    "p95_ms": s["ttfa_p95_ms"],
                    "under_350": s["under_350"],
                    "samples": s["ttfa_samples"],
                    "rtf": s["rtf_median"],
                    "vram_mb": s["peak_allocated_mb"],
                }
            )
    agg = {"probe": "probe_prefill_levers", "gpu_name": gpu, "results": rows}
    path = OUT / "probe_prefill_levers.json"
    path.write_text(json.dumps(agg, indent=2) + "\n")
    best = min(rows, key=lambda r: r["p95_ms"])
    print("best", json.dumps(best))
    print("PREFILL_LEVERS_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
