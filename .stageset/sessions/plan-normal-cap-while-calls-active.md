# READY plan: normal-batch cap while calls are active

Status: READY (plan only, no code)

## Trigger
- Mixed test (128 call first-only + 32 normal, local T4, in-process): call first-byte p95 581.38 ms (>350 ms), normal p95 826.37 ms, 0 errors.
- Current policy: `call_first > call_cont > normal`, with busy cap `normal_busy_max_batch=32`, `normal_busy_max_frames=96` (job_classes defaults). Normal jobs still wait behind call batches.

## Plan
1. Add a hard normal admission gate while `active_call_sessions > 0`:
   - Option A: do not start a NORMAL batch if any `CALL_FIRST` or `CALL_CONT` job is queued (starve normal, protect calls).
   - Option B: allow one small NORMAL batch only when call queues empty for `N` ms (e.g. 20-50 ms).
2. Keep normal request latency bounded separately: return 503/retry-after for normal when call load is high, or expose a normal queue limit.
3. Measure after change: call first-byte p95 at 128/224 with 32 normal; normal p95 and error/503 rate.
4. Do not change call priorities. Do not change call chunking.

## Acceptance
- Call first-byte p95 <= 350 ms in mixed test (128 call first-only + 32 normal).
- Normal behavior documented (latency or controlled rejection), no stuck queue, active_call_sessions returns to 0.
