"""Generate FP32 and FP16 quality WAVs for manual listening.

Run: python Code/probes/make_fp16_quality_wavs.py
Writes: Code/probes/out/fp16_quality/*.wav
"""

import logging
import os
import sys
from pathlib import Path

import soundfile as sf
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
sys.path.insert(0, str(REPO / "Code" / "probes"))
os.chdir(REPO / "Code" / "model")

logging.disable(logging.CRITICAL)
from pocket_tts import TTSModel  # noqa: E402
from batch.batched_stream import BatchedStream  # noqa: E402
from batch.fp16 import enable_fp16_backbone  # noqa: E402

VOICE = REPO / "Code" / "probes" / "ref" / "voice.wav"
OUT = REPO / "Code" / "probes" / "out" / "fp16_quality"

EN0 = "The quick brown fox jumps over the lazy dog near the river bank."
EN1 = "We tested the batched model with a short sentence and a calm voice."
HI = "नमस्ते, यह एक छोटा वाक्य है जो साफ़ और धीरे बोला गया है।"
MR = "नमस्कार, हे एक छोटे वाक्य आहे जे स्पष्ट आणि हळू बोलले आहे."


def load(fp16: bool):
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    if fp16:
        enable_fp16_backbone(model)
    return model


def gen(model, texts, max_frames=None):
    stream = BatchedStream(model, VOICE)
    audio = stream.stream(texts, max_frames=max_frames)
    return [a.cpu().numpy().reshape(-1) for a in audio]


def save(name, audio):
    sf.write(OUT / f"{name}.wav", audio, 24000)
    print(f"{name}.wav  {len(audio) / 24000:.2f}s")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    m32 = load(False)
    m32.temp = 0.0
    save("fp32_b1_t0", gen(m32, [EN0])[0])
    save("fp32_hi", gen(m32, [HI])[0])
    save("fp32_mr", gen(m32, [MR])[0])
    m32.temp = 1.0
    save("fp32_b1_t1", gen(m32, [EN1])[0])
    del m32
    torch.cuda.empty_cache()

    m16 = load(True)
    m16.temp = 0.0
    save("fp16_b1_t0", gen(m16, [EN0])[0])
    save("fp16_b32_row0_t0", gen(m16, [EN0] * 32)[0])
    save("fp16_hi", gen(m16, [HI])[0])
    save("fp16_mr", gen(m16, [MR])[0])
    m16.temp = 1.0
    save("fp16_b1_t1", gen(m16, [EN1])[0])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
