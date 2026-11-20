---
type: CODING
time: 2026-11-20T22:52:00+05:30
summary: Implement call-mode job classes and chunker through SSLD-018 and SSLD-019. All checks pass.
paths: Code/batch/job_classes.py; Code/batch/call_chunker.py; Skeletons/Code/batch/job_classes.py; Skeletons/Code/batch/call_chunker.py; LivingDocs/SSLD-018-call-mode-job-classes.md; LivingDocs/SSLD-019-call-mode-chunker.md
related: IDEA-0007; SSLD-018; SSLD-019; 20261120-225006-RUN; 20261120-225006-RUN-02; 20261120-225006-RUN-03; 20261120-225006-RUN-04
commit: -
remote: -
branch: -
---

# Session notes

## Work done

- Ran SSLD-018. Created `Code/batch/job_classes.py`.
- Ran SSLD-019. Created `Code/batch/call_chunker.py`.
- Both documents are DONE. All four tasks in each document pass.

## Evidence

- CHECK-CALL-CLASS-01 PASS: `.stageset/runs/20261120-225006-RUN.md`.
- CHECK-CALL-CLASS-02 PASS: `.stageset/runs/20261120-225006-RUN-02.md`.
- CHECK-CALL-CHUNK-01 PASS: `.stageset/runs/20261120-225006-RUN-03.md`.
- CHECK-CALL-CHUNK-02 PASS: `.stageset/runs/20261120-225006-RUN-04.md`.

## Skeleton state

- `Skeletons/Code/batch/job_classes.py` implemented revision 1.
- `Skeletons/Code/batch/call_chunker.py` implemented revision 1.

## Next

- Write SSLD-020 for `Skeletons/Code/batch/server.py` revision 10.
- Wire `/ws/tts`, class routing, and the debug ramp routes.
- Then run `probe_call_ceiling.md` and `probe_call_mode.md`.

## Open

- A-43 (first chunk fits 24 to 48 frames) and A-44 (audible seam) are not
  checked yet. The probes and the listening gate must check them.
