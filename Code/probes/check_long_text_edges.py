"""Check long-text chunks on hard text shapes. Check frame estimates too."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.getenv("ARSENAL_POCKET_TTS"):
    sys.path.insert(0, os.environ["ARSENAL_POCKET_TTS"])
os.chdir(Path(__file__).resolve().parents[1] / "model")
logging.disable(logging.CRITICAL)

import torch

from pocket_tts import TTSModel

from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights

VOICE = str(Path(__file__).resolve().parent / "ref" / "voice.wav")
OUT = Path(__file__).resolve().parent / "out" / "check_long_text_edges.json"
MAX_FRAMES = 192

TEXTS = {
    "multi_sentence": (
        "The quick brown fox jumps over the lazy dog near the river. "
        "A silver train leaves the station at noon every single day. "
        "Please close the windows before the storm arrives."
    ),
    "one_long_sentence": (
        "This single sentence keeps going without a full stop so the "
        "chunker must split it on a word boundary and keep every word in "
        "the correct order even when the first chunk reaches its token cap."
    ),
    "abbreviations": "Dr. Smith paid 3.14 dollars on Jan. 5, 2026. Mr. Rao agreed.",
    "mixed_language": "Hello, नमस्ते दुनिया। This is a mixed language test. धन्यवाद।",
    "punctuation": "Wait... what?! Yes; no: maybe. (This is fine.)",
    "long_repeat": " ".join(
        ["The river is quiet and the small boat moves slowly under the bridge."] * 12
    ),
}


def load() -> tuple[object, BatchedStream]:
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    model.temp = 0.0
    enable_fp16_backbone(model, mimi_fp16=True)
    weights = Path("fp16_weights.pt")
    if weights.exists():
        load_fp16_weights(model, weights)
    stream = BatchedStream(
        model,
        voice=VOICE,
        voice_seconds=4.0,
        max_first_tokens=16,
        max_allowed_frames=MAX_FRAMES,
    )
    return model, stream


def norm_words(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^\w\u0900-\u097f]+", " ", text)
    return [w for w in text.split() if w]


def main() -> int:
    result: dict[str, object] = {"texts": {}, "max_frames": MAX_FRAMES}
    model, stream = load()

    for name, text in TEXTS.items():
        row: dict[str, object] = {}
        try:
            chunks = stream._text_chunks(text)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["ok"] = False
            result["texts"][name] = row
            continue
        expected = norm_words(text)
        actual = norm_words(" ".join(chunks))
        frames = [
            max(model._estimate_max_gen_len(len(stream._text_ids(c))) for c in [chunk]) + 8
            for chunk in chunks
        ]
        row.update(
            {
                "chunk_count": len(chunks),
                "words": len(expected),
                "missing": [w for w in expected if w not in actual],
                "order_ok": expected == actual,
                "frame_estimates": frames,
                "frames_fit": all(f <= MAX_FRAMES for f in frames),
            }
        )
        row["ok"] = bool(
            row["order_ok"] and not row["missing"] and row["frames_fit"]
        )
        result["texts"][name] = row

    torch.cuda.reset_peak_memory_stats()
    audio = stream.stream([TEXTS["long_repeat"]])
    torch.cuda.synchronize()
    result["long_repeat_samples"] = int(audio[0].numel())
    result["long_repeat_peak_gib"] = round(
        torch.cuda.max_memory_allocated() / 2**30, 3
    )
    result["long_repeat_audio_ok"] = audio[0].numel() > 0

    result["ok"] = bool(
        all(row.get("ok") for row in result["texts"].values())
        and result["long_repeat_audio_ok"]
        and result["long_repeat_peak_gib"] < 15.0
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "texts": len(TEXTS)}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
