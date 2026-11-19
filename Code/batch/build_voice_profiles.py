"""Build conditioned voice profiles for the image or server.

Run at image build time:

    python Code/batch/build_voice_profiles.py Code/model/voice_profiles \
        alba=voices/alba.wav casual=voices/casual.wav

Then set:

    ARSENAL_VOICE_PROFILES="alba=Code/model/voice_profiles/alba.pt;casual=Code/model/voice_profiles/casual.pt"

A request selects a profile with the `voice_profile` field. Without that field,
the server uses the reference voice clip on the normal path.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: build_voice_profiles.py OUT_DIR id=path [id=path ...]")
        return 2
    out_dir = Path(argv[1])
    code_root = Path(__file__).resolve().parents[1]
    repo_root = code_root.parent
    specs: list[tuple[str, Path]] = []
    for spec in argv[2:]:
        if "=" not in spec:
            print(f"SKIP {spec}: expected id=path")
            return 2
        name, path = spec.split("=", 1)
        voice = Path(path)
        if not voice.is_absolute():
            voice = (repo_root / voice).resolve()
        specs.append((name.strip(), voice))
    sys.path.insert(0, str(code_root))
    extra = os.getenv("ARSENAL_POCKET_TTS")
    if extra:
        sys.path.insert(0, extra)
    model_dir = Path(os.getenv("ARSENAL_MODEL_DIR", code_root / "model"))
    os.chdir(model_dir)
    logging.disable(logging.CRITICAL)

    import torch

    from pocket_tts import TTSModel

    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from batch.fp16_weights import load_fp16_weights

    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=True)
    weights = Path("fp16_weights.pt")
    if weights.exists():
        load_fp16_weights(model, weights)

    out_dir.mkdir(parents=True, exist_ok=True)
    seconds = float(os.getenv("ARSENAL_VOICE_SECONDS", "4.0"))
    for name, path in specs:
        stream = BatchedStream(
            model,
            voice=str(path),
            voice_seconds=seconds,
            max_first_tokens=int(os.getenv("ARSENAL_FIRST_TOKENS", "16")),
        )
        target = out_dir / f"{name.strip()}.pt"
        stream.save_voice_profile(target, conditioned=True)
        print(f"PROFILE {name.strip()} {target}")
    torch.cuda.synchronize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
