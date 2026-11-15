"""Compare batched stream audio with the reference generate_audio path.

Run: python Code/probes/cmp_reference_audio.py
Writes: Code/probes/out/cmp_reference_audio.json
Prints: DECODER PARITY PASS or DECODER PARITY FAIL
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

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
TEXT = "The quick brown fox jumps over the lazy dog near the river bank."


def main() -> int:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    model.temp = 0.0

    state = model.get_state_for_audio_prompt(str(VOICE))
    ref = model.generate_audio(state, TEXT).cpu().reshape(-1)
    batched = BatchedStream(model, VOICE).stream([TEXT])[0].cpu().reshape(-1)

    n = min(ref.numel(), batched.numel())
    corr = float(torch.corrcoef(torch.stack([ref[:n], batched[:n]]))[0, 1])
    diff = float((ref[:n] - batched[:n]).abs().max())
    ok = corr > 0.99

    out = {
        "corr": corr,
        "max_abs_diff": diff,
        "ref_samples": int(ref.numel()),
        "batched_samples": int(batched.numel()),
        "result": "PASS" if ok else "FAIL",
    }
    path = REPO / "Code" / "probes" / "out" / "cmp_reference_audio.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print("DECODER PARITY PASS" if ok else "DECODER PARITY FAIL")
    print(json.dumps(out, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
