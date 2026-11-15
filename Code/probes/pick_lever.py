"""Pick one voice and chunk pair from the randomized lever probe.

Run: python Code/probes/pick_lever.py
Prints: BEST voice=... cap=... or NO SAFE PAIR
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / "Code" / "probes" / "out" / "probe_prefill_random.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(PATH))
    args = parser.parse_args()
    data = json.loads(Path(args.path).read_text())
    groups = defaultdict(dict)
    for row in data["results"]:
        groups[(row["voice_seconds"], row["first_tokens"])][row["batch"]] = row
    candidates = []
    for (voice, cap), by_batch in groups.items():
        if 96 not in by_batch or 128 not in by_batch:
            continue
        a, b = by_batch[96], by_batch[128]
        fa = a["under_350"] / a["samples"]
        fb = b["under_350"] / b["samples"]
        if a["p95_ms"] < 350 and b["p95_ms"] < 350 and fa >= 0.95 and fb >= 0.95:
            candidates.append((max(a["p95_ms"], b["p95_ms"]), voice, cap, a["p95_ms"], b["p95_ms"]))
    if not candidates:
        print("NO SAFE PAIR")
        return 1
    candidates.sort(key=lambda x: (round(x[0], 1), -x[1]))
    _, voice, cap, p96, p128 = candidates[0]
    print(f"BEST voice={voice} cap={cap} p95_b96={p96} p95_b128={p128}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
