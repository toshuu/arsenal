"""Generate parity audio with original or patched vendor pocket-tts."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch

ROOT = Path("/kaggle/working/arsenal-trt-sideline")
TEXTS = [
    "Hello, can you hear me clearly right now?",
    "The quick brown fox jumps over the lazy dog.",
    "Please call me back when you have a moment.",
    "This is a longer test sentence that should cover several clauses, and it continues here to check the cache over time.",
    "One two three four five six seven eight nine ten.",
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--vendor", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    out = Path(args.out).resolve()
    sys.path.insert(0, args.vendor)
    sys.path.insert(0, str(ROOT / "Code"))
    os.chdir(ROOT / "Code" / "model")
    from pocket_tts import TTSModel
    from batch.batched_stream import BatchedStream
    from batch.fp16 import enable_fp16_backbone
    from batch.fp16_weights import load_fp16_weights

    torch.manual_seed(11)
    model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
    enable_fp16_backbone(model, mimi_fp16=True)
    load_fp16_weights(model, Path("fp16_weights.pt"))
    for module in model.modules():
        if isinstance(module, torch.nn.LayerNorm) and module.weight is not None:
            if module.weight.dtype == torch.float32:
                module.weight.data = module.weight.data.half()
                if module.bias is not None:
                    module.bias.data = module.bias.data.half()
    model.temp = 0.0
    stream = BatchedStream(
        model, voice="/kaggle/working/refHD.wav", voice_seconds=4.0, max_first_tokens=16
    )
    out.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(TEXTS):
        audio = stream.stream([text], max_frames=224)[0].detach().float().cpu()
        torch.save(audio, out / f"text_{i}.pt")
        print("AUDIO", i, audio.numel(), round(float(audio.abs().max()), 5), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
