---
type: CODING
time: 2026-11-20T23:22:00+05:30
summary: Run local T4 call ramp, mixed, and cancel probes with the debug routes. Record results and facts.
paths: probes/out/callramp_b224_mf32_w10.json; probes/out/callmixed_c128_n32.json; probes/out/callcancel_b128.json
related: IDEA-0007; SSLD-021; FACT-0130; FACT-0131; 20261120-231834-RUN; 20261120-231834-RUN-02
commit: -
remote: -
branch: -
---

# Session notes

## Work done

- Installed `pocket_tts` from `/kaggle/working/pocket-tts` with `--no-deps`.
- Ran in-process call debug probes on Tesla T4 (GPU 0).
- Saved ramp sweep JSON for `max_frames` 24,32 and `window` 0,5,10,25 at B=64,128,224. Saved mixed and cancel JSON.

## Evidence

- Ramp: `.stageset/runs/20261120-231834-RUN.md`.
- Mixed/cancel: `.stageset/runs/20261120-231834-RUN-02.md`.

## Skeleton state

- `Skeletons/Probes/probe_call_ceiling.md` and `Skeletons/Probes/probe_call_mode.md` remain READY, implemented revision 0. Local runs are not the full Modal in-container gates.
