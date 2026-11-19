"""Check the voice and first-chunk levers.

Run: python Code/probes/check_batch_levers.py
Prints: CHECK_BATCH_LEVERS PASS or CHECK_BATCH_LEVERS FAIL
"""

import logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)

from pocket_tts import TTSModel  # noqa: E402
from batch.batched_stream import BatchedStream  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
TEXT = "The old sailor found a brass key near the harbor, and he waited for the morning train."


def main() -> int:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    full = BatchedStream(model, VOICE)
    short = BatchedStream(model, VOICE, voice_seconds=2.0)
    capped = BatchedStream(model, VOICE, max_first_tokens=8)
    full_frames = full.voice.shape[1]
    short_frames = short.voice.shape[1]
    full_chunk = full._text_chunks(TEXT)[0]
    cap_chunk = capped._text_chunks(TEXT)[0]
    full_tokens = len(full._text_ids(full_chunk))
    cap_tokens = len(capped._text_ids(cap_chunk))
    ok = short_frames < full_frames and cap_tokens < full_tokens
    print("CHECK_BATCH_LEVERS PASS" if ok else "CHECK_BATCH_LEVERS FAIL")
    print(f"voice_frames full={full_frames} short={short_frames}")
    print(f"first_chunk_tokens full={full_tokens} capped={cap_tokens}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
