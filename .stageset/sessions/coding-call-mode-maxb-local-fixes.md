---
type: CODING
time: 2026-11-21 12:03 +0530
summary: Fix call-mode measurement/server, run local burst/Poisson/mixed/WAV probes, record Modal attempt.
paths: Code/batch/server.py; Code/batch/batched_stream.py; Code/probes/call_load_client.py; Code/probes/probe_call_cases.py; Code/probes/probe_call_modal_run.py; Code/probes/make_call_wavs.py; Code/probes/check_call_ws.py; .stageset/runs/20261121-120307-RUN.md; .stageset/runs/20261121-120353-RUN.md; .stageset/runs/20261121-120353-RUN-02.md; .stageset/runs/20261121-120353-RUN-03.md; .stageset/runs/20261121-120354-RUN.md; .stageset/runs/20261121-120354-RUN-02.md; .stageset/runs/20261121-120354-RUN-03.md; .stageset/facts.md; .stageset/reports/20261121-call-mode-local-maxb/results.json; Code/probes/out/call_mode/call_mf8_0.wav; Code/probes/out/call_mode/call_mf8_1.wav; Code/probes/out/call_mode/call_mf8_2.wav; Code/probes/out/call_mode/call_mf8_3.wav; Code/probes/out/call_mode/call_mf8_4.wav; Code/probes/out/call_mode/call_mf6_0.wav; Code/probes/out/call_mode/call_mf6_1.wav; Code/probes/out/call_mode/call_mf6_2.wav; Code/probes/out/call_mode/call_mf6_3.wav; Code/probes/out/call_mode/call_mf6_4.wav
related: IDEA-0007; Skeletons/Probes/probe_call_ceiling.md; Skeletons/Probes/probe_call_mode.md; 20261121-120307-RUN; 20261121-120353-RUN; 20261121-120353-RUN-02; 20261121-120353-RUN-03; 20261121-120354-RUN; 20261121-120354-RUN-02; 20261121-120354-RUN-03
commit: -
remote: -
branch: -
---

# Session notes

## Decisions
- Measure call first byte as send->first audio byte. Connect/start measured separately.
- Pre-connect WS clients and use barrier before text send for burst tests.
- Stream first call chunk frames over WS to reduce time-to-first-byte.
- Add `/debug/drain` and early call-first flush when batch reaches active sessions.

## Outcomes
- `check_call_ws.py` passes. Local T4 burst (mf8, fresh server, pre-connected): B256 cli p95-of-p95 272.7 ms, B320 343.2 ms (pass <350), B384 425.0 ms, B448 483.1 ms, 0 errors.
- Poisson 256/320/384 (30s, per-request WS) failed 350 ms gate with high connect/start and ~185 rows/s. 384/s had 1056 errors.
- Mixed 128 call + 32 normal debug: call first-byte p95 546.9 ms, normal p95 3164.3 ms, 0 errors.
- 10 joined WAVs saved (mf8/mf6, 3 chunks each); objective scan flags possible clipped endings in mf8_3 and mf6_0/3/4. Owner listening not done.
- Connect investigation: TCP ~0.03 ms, sequential WS start ~2.5 ms total; burst connect/start grows to 224-434 ms p95 at B256-448 due concurrent handshake/accept contention.
- Modal credentials set and `modal run call_probe` started but remote input canceled; no Modal case JSON captured.

## Follow-up
- Rerun Modal in-container cases with incremental artifact output and stop after completion.
- Improve Poisson/mixed with persistent sessions or isolation/preemption.
- Owner listens to `Code/probes/out/call_mode/` WAVs.
