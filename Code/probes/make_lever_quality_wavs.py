"""Generate quality WAVs for the voice length lever.

Run: python Code/probes/make_lever_quality_wavs.py
Writes: Code/probes/out/lever_quality/*.wav
"""

import logging
import os
import sys
from pathlib import Path

import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)

from pocket_tts import TTSModel  # noqa: E402
from batch.batched_stream import BatchedStream  # noqa: E402
from batch.fp16 import enable_fp16_backbone  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
OUT = REPO / "Code" / "probes" / "out" / "lever_quality"
TEXT = "The quick brown fox jumps over the lazy dog."


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, use_fp16 in (("fp32", False), ("fp16", True)):
        model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
        if use_fp16:
            enable_fp16_backbone(model)
        model.temp = 0.0
        for voice_seconds in (6.5, 3.0, 2.0):
            stream = BatchedStream(model, VOICE, voice_seconds=voice_seconds, max_first_tokens=24)
            audio = stream.stream([TEXT])[0].cpu().numpy().reshape(-1)
            path = OUT / f"{name}_voice{voice_seconds}_chunk24.wav"
            sf.write(path, audio, 24000)
            print(path.name, round(len(audio) / 24000, 2))
    print("LEVER_QUALITY_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
