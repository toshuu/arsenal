"""Read-only parity check: original vs patched attention cache functions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import torch

SIDELINE = Path("/kaggle/working/arsenal-trt-sideline")
ORIG_FILE = Path("/kaggle/working/pocket-tts/pocket_tts/modules/attention.py")
sys.path.insert(0, str(SIDELINE / "vendor" / "pocket-tts"))

spec = importlib.util.spec_from_file_location("attn_orig", str(ORIG_FILE))
assert spec and spec.loader
orig = importlib.util.module_from_spec(spec)
sys.modules["attn_orig"] = orig
spec.loader.exec_module(orig)

import pocket_tts.modules.attention as patched

torch.manual_seed(7)
failures = []

for batch in (1, 8, 256):
    for t in (1, 3):
        for start in (0, 5, 37):
            heads, dim, cap = 4, 8, 64
            cache = torch.full((2, batch, cap, heads, dim), float("nan"), device="cuda")
            offset = torch.full((batch,), start, dtype=torch.long, device="cuda")
            pad = torch.zeros(batch, dtype=torch.long, device="cuda")
            k = torch.randn(batch, t, heads, dim, device="cuda")
            v = torch.randn(batch, t, heads, dim, device="cuda")

            a = orig.complete_kv(cache.clone(), offset.clone(), k, v)
            b = patched.complete_kv(cache.clone(), offset.clone(), k, v)
            b_valid = b[0][:, : start + t], b[1][:, : start + t]
            close = torch.allclose(a[0], b_valid[0], atol=1e-6, equal_nan=True) and torch.allclose(
                a[1], b_valid[1], atol=1e-6, equal_nan=True
            )
            if not close:
                failures.append(f"complete_kv B={batch} t={t} start={start}")

            backend_orig = orig._LinearKVCacheBackend(heads, dim)
            backend_patch = patched._LinearKVCacheBackend(heads, dim)
            state = {"cache": cache.clone(), "offset": offset.clone(), "pad": pad.clone()}
            oa = backend_orig.append_and_get(k, v, state)
            ob = backend_patch.append_and_get(k, v, state)
            n = start + t
            if not (
                torch.allclose(oa[0][:, :, :n], ob[0][:, :, :n], atol=1e-6, equal_nan=True)
                and torch.allclose(oa[1][:, :, :n], ob[1][:, :, :n], atol=1e-6, equal_nan=True)
                and torch.allclose(oa[2][:, :n], ob[2][:, :n])
                and torch.equal(oa[3], ob[3])
            ):
                failures.append(f"append_and_get B={batch} t={t} start={start}")

print("PARITY_FAILURES", failures)
print("PARITY_OK" if not failures else "PARITY_BAD")
sys.exit(1 if failures else 0)
