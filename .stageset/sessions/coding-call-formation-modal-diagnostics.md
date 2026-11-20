---
type: CODING
time: 2026-11-20T20:38:41+00:00
summary: End session 20 Nov 18:00-21 Nov ~02:00: add WS load client and Modal in-container probe, run local formation/Poisson consolidation and 3 Modal T4 diagnostic runs, document all artifacts and gaps.
paths: Code/deploy/modal_app.py; Code/probes/call_load_client.py; Code/probes/probe_call_modal_run.py; Code/probes/out/formation_grace_local.json; Code/probes/out/trust_poisson_30s.json; .stageset/reports/20261120-call-mode-complete/; .stageset/runs/20261121-020840-RUN.md; .stageset/runs/20261121-020840-RUN-02.md; .stageset/runs/20261121-020840-RUN-03.md; .stageset/runs/20261121-020840-RUN-04.md
related: IDEA-0007; FACT-0134; FACT-0135; FACT-0136; FACT-0137; 20261121-020840-RUN; 20261121-020840-RUN-02; 20261121-020840-RUN-03; 20261121-020840-RUN-04
commit: -
remote: -
branch: -
---

# Session notes

## Work done

- Added `Code/probes/call_load_client.py` (separate-process WS `/ws/tts` burst/Poisson, first-byte, later connect/started timing) and `Code/probes/probe_call_modal_run.py`; wired `call_probe` dev function in `Code/deploy/modal_app.py` for in-container Modal runs (server pinned cores 0-3, client 4-7).
- Consolidated local evidence: formation grace (`formation_grace_local.json`) — B=256 grace10 stable 1-batch 197/199 ms; B=320/384 near <350 median with splits/tails; Poisson 30s (`trust_poisson_30s.json`) <350 up to 224/s (324 ms), 288/s 367 ms; truncation check showed short clauses fit mf6/mf8.
- Ran 3 Modal T4 8CPU in-container probe attempts (logs + extracted partial JSON in `.stageset/reports/20261120-call-mode-complete/`): server-side callramp steady reps 177-259 ms median p95 for B=256-384, but WS client e2e 1.4-2.0s median p95; connect/start 150-500 ms; active_call_sessions/call_cont contamination observed (debug first_only cont backlog). Poisson/mixed/B=448 not cleanly captured.
- Stopped Modal apps after runs; `modal container list` empty.

## Evidence

- `.stageset/reports/20261120-call-mode-complete/summary.json`
- `.stageset/reports/20261120-call-mode-complete/HANDOFF_20261121.md`
- `.stageset/reports/20261120-call-mode-complete/modal_call_probe1.log`
- `.stageset/reports/20261120-call-mode-complete/modal_call_probe2.log`
- `.stageset/reports/20261120-call-mode-complete/modal_call_probe3.log`

## Blocked / gaps

- Clean isolated Modal gate matrix incomplete: Poisson 256/320/384, burst 448, mixed 128+32, per-case JSON with required fields, outlier-cause logging, mf8/mf6 joined WAV listening samples not produced.
