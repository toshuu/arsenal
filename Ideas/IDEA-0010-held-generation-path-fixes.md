---
id: IDEA-0010
title: Held generation-path fixes - chunk context and max tokens
status: DISCOVERY
priority: P1
created_at: 2026-11-26T14:25:46+00:00
updated_at: 2026-11-26T14:25:46+00:00
created_in: .stageset/sessions/plan-held-generation-path-fixes.md
updated_in: .stageset/sessions/plan-held-generation-path-fixes.md
related_ideas: [IDEA-0009]
related_skeletons: []
---

# Held generation-path fixes - chunk context and max tokens

## Summary

Two generation-path changes were studied in the sidecar. Both are held. The
base Arsenal path works well in current tests, so no code or config behavior is
changed now. This document keeps the finding for later use.

The two held items are:

1. Chunk context continuity for split text.
2. `max_tokens=80` for call text.

## Decision

**Do not implement now.** Keep the base path as it is. Activate a held item
only if a real production sample shows word skipping, bad rhythm, or a clear
latency problem.

## Held fix 1 - chunk context continuity

### Finding

The sidecar tests showed that manual part splitting broke text context. Each
part was generated from the same voice state, with no previous words or
previous latents. This caused early EOS, skipped words, and broken rhythm.

The same bug class exists in the base serving path:

- `Code/batch/batched_stream.py:393` splits one text into chunks.
- `Code/batch/batched_stream.py:417` calls `_stream_single()` once per chunk round.
- `Code/batch/batched_stream.py:496` calls `init_states()` for every round.
- `Code/batch/server.py:1336`, `1541`, `1728`, and `1921` submit chunks as
  separate jobs in HTTP and WS paths.

Continuation chunks start from a fresh state. They do not carry previous chunk
latents or previous chunk text.

### Planned fix

Add carried state across chunks in `BatchedStream`. The implementation may use
carried KV state or forced previous latents. Teacher forcing is not required in
every case. The goal is context continuity, not a specific mechanism.

### Why held

Base-as-is generation worked well in recent CPU samples. A state change in the
batch path can alter TTFA, VRAM, and batch gates. No GPU is available now, so
those gates cannot be re-measured.

### Activation triggers

Activate this fix if any of these occur:

- A real call sample drops words at chunk joins.
- Listening finds a rhythm break between chunks.
- A customer-facing text fails repeatedly after text normalization.
- The owner asks to activate the fix.

### Verification plan before activation

1. New StageSet Idea, Skeleton, and ss-living-doc.
2. Fake-engine tests first.
3. CPU tests with the owner pair file and call texts.
4. GPU TTFA and VRAM test.
5. WS 32-client and 224-client gates.
6. Listening A/B against the current base path.

## Held fix 2 - `max_tokens=80`

### Finding

Base defaults:

- `Code/batch/batched_stream.py:86`: `max_tokens=50`.
- `Code/batch/server.py:55` and `:65`: sentence and latency modes use 50.
- `Code/batch/server.py:60`: utterance mode uses 512.
- `TTSEngine` does not pass `max_tokens`, so 50 applies in normal paths.

Sidecar CPU latency sweep, 4 texts x 5 values x 2 reps:

| max_tokens | First chunk median | Total wall median |
|---:|---:|---:|
| 10 | 269.7 ms | 8114 ms |
| 25 | 257.2 ms | 8120 ms |
| 50 | 267.8 ms | 7866 ms |
| 80 | 255.6 ms | 8026 ms |
| 120 | 269.5 ms | 8039 ms |

80 gave the best first-chunk median and no chunk warnings. 50 gave the fastest
total wall by about 160 ms but warned on long text. 10 and 25 were not
usefully faster.

### Planned fix

1. Add `ARSENAL_MAX_TOKENS`, default 80.
2. Pass it from `TTSEngine` into `BatchedStream`.
3. Change sentence and latency call modes from 50 to 80.
4. Keep utterance mode at 512.
5. Keep teacher forcing off.
6. Keep 4 s ref default, which already exists at
   `Code/batch/server.py:1013` through `ARSENAL_VOICE_SECONDS=4.0`.

### Why held

Base-as-is samples are good. The latency gain is small and CPU-only. GPU and
batch effects are not measured. Changing the cap can alter frame budgets and
VRAM at high batch sizes.

### Verification plan before activation

1. New StageSet Skeleton and ss-living-doc.
2. Keep the 78-pair normalizer file green.
3. Run fake-engine checks.
4. Run CPU generation through the base `BatchedStream`.
5. Re-run GPU TTFA, VRAM, and batch gates.
6. Run a listening A/B against current base output.

## Items already in base

- Text normalization is in the base serving path. See `IDEA-0009`.
- 4 s ref voice default is in base.
- No teacher forcing is needed based on current evidence.

## Evidence files in sidecar

- `/kaggle/working/arsenal_hybrid_sidecar/TEACHER_FORCING_FINDING.md`
- `/kaggle/working/arsenal_hybrid_sidecar/out/LATENCY_MAX_TOKENS_REPORT.md`
- `/kaggle/working/arsenal_hybrid_sidecar/out/latency_raw.json`
- `/kaggle/working/arsenal_hybrid_sidecar/out/BASE_AS_IS_NOTE.md`

## Risks if activated too early

- TTFA regression at high batch.
- VRAM increase from larger frame estimates.
- Batch gate failure on T4.
- Rhythm change that owner dislikes.

## Related files

- `Ideas/IDEA-0009-text-normalization.md`
- `Code/batch/batched_stream.py`
- `Code/batch/server.py`
