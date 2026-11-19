"""Check full-text coverage, the frame guard, and truncation detection."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1] / "model")
logging.disable(logging.CRITICAL)

import torch

from pocket_tts import TTSModel

from batch.batched_stream import BatchedStream
from batch.fp16 import enable_fp16_backbone
from batch.fp16_weights import load_fp16_weights

VOICE = str(Path(__file__).resolve().parent / "ref" / "voice.wav")
OUT = Path(__file__).resolve().parent / "out" / "check_long_text.json"

TEXT = (
    "The quick brown fox jumps over the lazy dog near the river. "
    "A silver train leaves the station at noon every single day. "
    "Please remember to close the windows before the storm arrives."
)


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
        max_allowed_frames=192,
    )
    return model, stream


def words(text: str) -> set[str]:
    return {w.strip(".,!?;:\"'()").lower() for w in text.split() if w.strip(".,!?;:\"'()")}


def main() -> int:
    result: dict[str, object] = {}
    model, stream = load()

    chunks = stream._text_chunks(TEXT)
    joined = " ".join(chunks).lower()
    missing = sorted(w for w in words(TEXT) if w not in joined)
    result["chunks"] = chunks
    result["chunk_count"] = len(chunks)
    result["missing_words"] = missing
    result["coverage_ok"] = not missing

    from pocket_tts.models.text_chunking import prepare_text_prompt

    prepared, _ = prepare_text_prompt(
        TEXT,
        model.pad_with_spaces_for_short_inputs,
        model.remove_semicolons,
        model.append_terminal_punctuation,
        model.capitalize_first_letter,
        model.replace_characters,
    )
    full_tokens = model.flow_lm.conditioner.tokenizer.encode(prepared)
    result["full_token_count"] = len(full_tokens)

    stream.max_allowed_frames = 16
    guard_ok = False
    try:
        stream._stream_single(["Hello there."], max_frames=32)
    except ValueError as exc:
        guard_ok = "max_allowed_frames" in str(exc)
        result["guard_error"] = str(exc)
    result["guard_ok"] = guard_ok

    chunk_guard_ok = False
    try:
        stream._text_chunks(TEXT)
    except ValueError as exc:
        chunk_guard_ok = "too small" in str(exc)
        result["chunk_guard_error"] = str(exc)
    result["chunk_guard_ok"] = chunk_guard_ok
    stream.max_allowed_frames = 192

    torch.cuda.reset_peak_memory_stats()
    full = stream.stream([TEXT])
    torch.cuda.synchronize()
    result["full_samples"] = int(full[0].numel())
    result["full_seconds"] = round(full[0].numel() / model.config.mimi.sample_rate, 3)
    result["full_peak_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 3)

    torch.cuda.reset_peak_memory_stats()
    first = stream.stream([chunks[0]])
    torch.cuda.synchronize()
    result["first_samples"] = int(first[0].numel())
    result["first_seconds"] = round(first[0].numel() / model.config.mimi.sample_rate, 3)
    result["longer_than_first"] = full[0].numel() > first[0].numel() * 1.5

    stream.last_truncated_rows = []
    stream._stream_single([TEXT], max_frames=4)
    result["explicit_truncation_rows"] = stream.last_truncated_rows

    result["ok"] = bool(
        result["coverage_ok"]
        and guard_ok
        and chunk_guard_ok
        and result["longer_than_first"]
        and result["explicit_truncation_rows"]
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "chunks": result["chunk_count"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
