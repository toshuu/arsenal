---
type: IDEATION
time: 2026-11-20T22:45:00+05:30
summary: Approve dual-mode plan. Answer the B question. Add call-mode skeletons and probes.
paths: Ideas/IDEA-0007-dual-service-call-mode.md; Skeletons/Code/batch/job_classes.py; Skeletons/Code/batch/call_chunker.py; Skeletons/Code/batch/server.py; Skeletons/Probes/probe_call_ceiling.md; Skeletons/Probes/probe_call_mode.md
related: IDEA-0007; FACT-0119; FACT-0120; FACT-0121; FACT-0123; FACT-0124; FACT-0125; FACT-0126
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep both modes on one engine. Normal HTTP stays unchanged. Call mode uses a
  WebSocket for voice calls.
- The call gate is first-chunk p95 at max B. Continuation must have 0 underruns.
- A short first chunk (4 to 8 words, 24 to 48 frames) is correct for calls.
- Measure the B ceiling before code. Use the existing in-container selfprobe.
- No model change, no second worker, no CUDA graph.

## Answer to the B question

- B goes up a lot. Short first chunks use less memory and less batch time.
- B is not unlimited. The wall moves to CPU ingress, batch window, and queue
  behind a running batch.
- Estimated max B: 400 to 1024+ at 350 ms, 224 to 400 at 200 ms, 100 to 224 at
  100 ms. These are estimates. Probe `probe_call_ceiling.md` must measure them.

## Artifacts

- IDEA-0007 is APPROVED.
- `Skeletons/Code/batch/job_classes.py` revision 1 is READY.
- `Skeletons/Code/batch/call_chunker.py` revision 1 is READY.
- `Skeletons/Code/batch/server.py` revision 10 is READY, implemented revision 8.
- `Skeletons/Probes/probe_call_ceiling.md` is READY.
- `Skeletons/Probes/probe_call_mode.md` is READY.

## Order

1. Run `probe_call_ceiling.md` on the T4. Answer the B question with data.
2. Code `job_classes.py` and `call_chunker.py`. Pass their checks.
3. Code `server.py` revision 10. Pass the normal HTTP checks.
4. Run `probe_call_mode.md`. Record facts.
5. Stop the app.

## Open

- Seam quality needs an owner listening gate.
- If a normal batch blocks `call_first` above 350 ms, write a READY preemption plan.
  Do not code preemption without owner approval.
