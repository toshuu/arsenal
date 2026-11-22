---
type: CODING
time: 2026-11-22T19:36:14+00:00
summary: Fix frame-cap unit mismatch in WS latency mode: 24 frames now give 1.92 s.
paths: Code/batch/server.py
related: IDEA-0008; 20261122-235919-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Problem

- The page cap is in audio frames (80 ms each). The engine `max_frames` is in
  flow steps. One flow step produces two audio frames.
- Cap 24 gave 48 frames (3.84 s) and cap 56 gave 104 frames (8.32 s). The cap
  was not applied as the user expected.

## Fix

- In the WS handler, convert `max_frames`, `first_max_frames`, and `min_frames`
  from audio frames to flow steps with integer division by 2.
- Keep the engine path unchanged. This matches the 2:1 observation.

## Result

- Full text, cap 24: 24 frames, 1.92 s, cap_hit=true, eos=false.
- Full text, cap 56: 52 frames, 4.16 s, cap_hit=true, eos=false.

## Notes

- No client-side word limit. The full text is sent as one job.
- Not committed.
