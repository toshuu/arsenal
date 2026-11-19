<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/overlap.py
@stageset source_idea: IDEA-0004
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 2
@stageset implemented_revision: 2
@stageset planned_in: .stageset/sessions/coding-ssld-014-overlap.md
@stageset last_updated_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset implemented_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: overlap decode

## Purpose

Run one GPU decode on a second CUDA stream. The next flow step can run on the
default stream at the same time.

This is lever M2 of `Ideas/IDEA-0004-ttfa-burst-gain.md`.

## Contract

- `OverlapDecoder(device)`:
  - Create one `torch.cuda.Stream` and one `torch.cuda.Event`.
- `launch(fn)`:
  - Run `fn` in the second stream.
  - Make the second stream wait for the current stream first.
  - Record the done event at the end.
- `wait()`:
  - Make the current stream wait for the done event.
  - Call `done.synchronize()` so the CPU can read the result.

## Edge cases

- A CUDA error in the closure appears only at `wait()`.
- Do not touch tensors from the closure before `wait()`.
- Do not call `wait()` between two decode launches. That removes the overlap.

## Checks

### CHECK-OVERLAP-01 - parity

- Command: `python Code/probes/check_overlap.py`
- Predicted output: `CHECK_OVERLAP PASS`
- Pass condition: exit code 0 and the exact line `CHECK_OVERLAP PASS`.
  The minimum row correlation must be 0.999 or more.
- Fail condition: any other output or a non-zero exit code.

### CHECK-OVERLAP-02 - no steady gain

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_overlap.json')); print(d['stages']['192']['steady_ms']['p50'] >= 65.4)"`
- Predicted output: `True`
- Pass condition: the command prints `True`. Overlap must stay off by default.
- Fail condition: the steady p50 at B=192 is below 65.4 ms.
  Measured result: 69.99 ms. M2 failed. The T4 SMs are shared.

## References

- `Ideas/IDEA-0004-ttfa-burst-gain.md`
- `LivingDocs/SSLD-014-overlap-decode.md`
