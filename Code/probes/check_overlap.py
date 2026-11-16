import json, logging, os, sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Code"))
os.chdir(REPO / "Code" / "model")
logging.disable(logging.CRITICAL)

from pocket_tts import TTSModel
from batch.batched_stream import BatchedStream

TEXTS = [
    "Hello, this is a short test sentence.",
    "Good morning. The weather is nice today.",
    "Testing one two three four five six seven eight nine ten.",
]

model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
model.temp = 0.0
voice = REPO / "Code/probes/ref/voice.wav"
plain = BatchedStream(model, voice=voice, voice_seconds=4.0, max_first_tokens=16)
over = BatchedStream(model, voice=voice, voice_seconds=4.0, max_first_tokens=16, overlap_decode=True)
a = plain.stream(TEXTS, max_frames=8)
b = over.stream(TEXTS, max_frames=8)
assert len(a) == len(b)
min_corr = 1.0
max_diff = 0.0
for x, y in zip(a, b):
    n = min(x.numel(), y.numel())
    assert n > 0
    c = torch.corrcoef(torch.stack([x[:n], y[:n]]))[0, 1].item()
    d = (x[:n] - y[:n]).abs().max().item()
    min_corr = min(min_corr, c)
    max_diff = max(max_diff, d)
report = {"min_corr": min_corr, "max_abs_diff": max_diff, "rows": len(a)}
(REPO / "Code/probes/out/check_overlap.json").write_text(json.dumps(report, indent=2))
print("CHECK_OVERLAP PASS" if min_corr > 0.999 and max_diff < 0.01 else "CHECK_OVERLAP FAIL")
print(json.dumps(report))
