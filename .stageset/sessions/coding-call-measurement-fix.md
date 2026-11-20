---
type: CODING
time: 2026-11-20T23:40:00+05:30
summary: Fix call measurement, add first-byte and first-only debug support, run split ramps, sub-batch and mf/window sweeps, mixed and seam checks on local T4.
paths: Code/batch/server.py; probes/out/call_test_a.json; probes/out/call_test_b.json; probes/out/call_subbatch.json; probes/out/call_sweep.json; probes/out/callmixed_first_only_c128_n32.json; probes/out/call_seam.json; .stageset/sessions/plan-normal-cap-while-calls-active.md
related: IDEA-0007; FACT-0133; 20261120-233425-RUN; 20261120-233425-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Work done

- Added `first_byte_ms` and `first_only`/`text` support to debug call routes.
- Added `ARSENAL_CALL_FIRST_SUB_BATCH` for call-first collection.
- Ran local T4 tests: first-only ramp, full streams, sub-batch sweep, mf/window sweep, truncation, mixed, and 5 WS seam WAVs.
- Wrote READY plan for normal-batch cap while calls are active. No priority change.

## Evidence

- `.stageset/runs/20261120-233425-RUN.md`
- `.stageset/runs/20261120-233425-RUN-02.md`

## Blocked

- Modal not installed and no credentials. Step 5 (Modal T4 in-container, Poisson+burst) not run.
