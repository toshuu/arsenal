---
type: CODING
time: 2026-11-15T19:45:00+05:30
summary: Start voice profiles (disk + conditioned-state reuse) in batched_stream.
paths: Code/batch/batched_stream.py
related: IDEA-0003
commit: -
remote: -
branch: -
---

# Session notes

## User request

- Add voice profiles: compute voice data once, save/load forever.
- Reuse conditioned voice state per burst (skip per-burst 4.0 s voice prompt work).
- Keep both modes: profile mode and normal 4.0 s path.

## Status

- `Code/batch/batched_stream.py` modified (WIP, uncommitted): profile load/save, conditioned-state clone and text-only conditioning path added.
- Not verified. Quick test shows output mismatch under sampling; correctness and TTFA gain must be checked (temp 0 / seeded parity, sustained TTFA).

## Next

- Verify parity and latency, then document in skeleton/SSLD.
