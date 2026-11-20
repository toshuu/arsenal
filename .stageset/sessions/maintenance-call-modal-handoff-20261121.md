---
type: MAINTENANCE
time: 2026-11-20T20:45:00+00:00
summary: End-of-session handoff for 2026-11-21 after 07:00 with Claude direction for clean Modal rerun/fixes.
paths: .stageset/reports/20261120-call-mode-complete/HANDOFF_20261121.md; .stageset/facts.md; .stageset/sessions-tracker.md; .stageset/DIGEST.md
related: IDEA-0007; FACT-0137; .stageset/reports/20261120-call-mode-complete/summary.json
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- End session (20 Nov 18:00 to 21 Nov ~02:00). Do not claim call-mode gate pass; document diagnostics and gaps completely.
- Next work session: 2026-11-21 after 07:00. Follow Claude direction before rerunning.

## Outcomes

- StageSet updated with runs, facts (FACT-0134–0137), copied probe logs/JSONs, summary, and handoff for tomorrow.

## Follow-up (Claude direction — continue)

1. `first_only` mode must NOT enqueue continuations. Add a drain wait (`queue_depth==0`, `active_call_sessions==0`) between every rep and phase.
2. Connect all WS clients and finish the start handshake BEFORE the barrier. Time only send -> first audio byte. Report connect time separately. Investigate why connect+start is 150-500 ms (accept loop, handshake, voice setup, CPU contention?).
3. Run each case as a separate job with a fresh server: burst 256/320/384/448 (10 reps), Poisson 256/320/384 (30 s), JSON per case (batches/rep, rows/s, p50/p95, queue p95, errors).
4. For the outlier reps (368, 430 ms): log whether a split or leftover load caused it.
5. Mixed 128 call + 32 normal only after the above, on separate instances if it still fails.
6. Save 5 joined WAV samples at mf8 and mf6 for a listening check.
7. Stop the app after: `modal app stop arsenal-tts-t4 -y`.

Report: `case | batches/rep | p50/p95 server | p50/p95 client | connect | errors`.
