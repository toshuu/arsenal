"""Build voice embedding cache at image time.

Run before the server starts. Set ARSENAL_VOICE_CACHE to the output directory.
Keep the output in the image or on a persistent volume. Do not rebuild on wake.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def build(cache_dir: str | Path | None = None) -> None:
    if cache_dir is None:
        cache_dir = os.getenv("ARSENAL_VOICE_CACHE", "Code/model/voice_cache")
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    os.environ["ARSENAL_VOICE_CACHE"] = str(cache_path)
    sys.path.insert(0, "Code")
    os.chdir("Code/model")
    logging.disable(logging.CRITICAL)
    from pocket_tts import TTSModel

    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from batch.fp16_weights import load_fp16_weights

    voice = Path("../probes/ref/voice.wav")
    weights = Path("fp16_weights.pt")
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=True)
    if weights.exists():
        load_fp16_weights(model, weights)
    BatchedStream(model, voice=str(voice), voice_seconds=4.0, max_first_tokens=16)
    print(f"VOICE_CACHE_BUILT {cache_path}")
