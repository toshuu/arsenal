"""Smoke check for Code/batch/batched_stream.py.

Run from the repository root:
  python Code/probes/check_batch_stream.py

It prints CHECK_BATCH_STREAM PASS on success and writes details to
Code/probes/out/check_batch_stream.json.
"""

import json
import logging
import os
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
os.chdir(REPO / "Code" / "model")

logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel  # noqa: E402

from batch.batched_stream import BatchedStream  # noqa: E402

TEXTS = [
    "Hello, this is a short test sentence.",
    "Good morning. The weather is nice today.",
    "Testing one two three four five six seven eight nine ten.",
]


def main() -> int:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    stream = BatchedStream(model, REPO / "Code" / "probes" / "ref" / "voice.wav")

    model.temp = 0.0
    single = stream.stream([TEXTS[0]], max_frames=8)[0]
    batched = stream.stream(TEXTS, max_frames=8)
    diff = float((single - batched[0]).abs().max())

    model.temp = 0.3
    first = {}

    def on_chunk(row, chunk, elapsed):
        if row not in first and float(chunk.abs().max()) > 0.01:
            first[row] = elapsed

    stream.stream(TEXTS, on_chunk=on_chunk, max_frames=12)
    ok = diff < 1e-3 and len(first) == len(TEXTS) and max(first.values()) < 0.35

    out = {
        "parity_max_abs_diff": diff,
        "first_sound_ms": {str(k): round(v * 1000, 2) for k, v in sorted(first.items())},
        "result": "PASS" if ok else "FAIL",
    }
    path = REPO / "Code" / "probes" / "out" / "check_batch_stream.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print("CHECK_BATCH_STREAM PASS" if ok else "CHECK_BATCH_STREAM FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
