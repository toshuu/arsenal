---
type: CODING
time: 2026-11-19T19:11:20+05:30
summary: Full-text chunking, frame guard, truncation reporting, HTTP server, sideline archive.
paths: Code/batch/batched_stream.py; Code/batch/server.py; Code/probes/check_long_text.py; Code/probes/check_server.py; Skeletons/Code/batch/batched_stream.py; Skeletons/Code/batch/server.py; Skeletons/Code/batch/overlap.py; Skeletons/Probes/probe_levers_inproc.md; Skeletons/Probes/probe_cold_start.md; scripts/stageset-status.py; .stageset/facts.md; Code/experiments/shrink/archive/README.md
related: IDEA-0005; FACT-0088; FACT-0089; FACT-0090; FACT-0091; FACT-0092
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Split every text into all chunks and generate them in order. Do not drop text.
- Enforce `max_allowed_frames` before state allocation.
- Fail loudly when an auto frame budget ends before EOS. Record explicit truncation rows.
- Add a bounded HTTP server with queue, timeout, disconnect stop, and limits.
- Archive the Mimi-swap experiment as a negative dtype result.
- Report only the latest run for each check in the digest and status.

## Outcomes

- A 69-token text gives 3 chunks and 10.8 s of audio. No word is missing.
- The guard raises `ValueError` for an over-limit request.
- The server passes health, single, batch, limit, timeout, and full-queue checks.
- The real engine returns a WAV on a T4.
- The three old negative checks now have revision 2 contracts that pass.
- `python scripts/stageset-status.py --validate` passes.

## Open items

- Modal build and L4 benchmark stay out of scope for this session.
