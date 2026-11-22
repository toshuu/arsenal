---
type: MAINTENANCE
time: 2026-11-22T15:54:42+00:00
summary: Diagnose the SSLD-030 measurement drift and plan a clean re-run.
paths: LivingDocs/SSLD-031-reliability.md; Skeletons/Probes/probe_ws_burst_gate.md; .stageset/runs/20261122-210000-RUN.md
related: IDEA-0008; SSLD-030; SSLD-031; 20261122-210000-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Problem

The SSLD-030 result is not valid.

- The executor edited `Code/probes/call_load_client.py`. The edit opens new
  connections for each repetition. It adds warm runs to the run list.
- The executor wrote fields into `gate.json` that the probe script does not
  produce. Example: `per_rep` and `warm_p95_max`.
- The reported `p95_of_p95` includes the first cold run and connection churn.
- The reported FAIL is not a server result. It is a measurement result.
- The 2.3 s and 3.2 s outliers are not stable. They are not in the committed
  probe path.

## Cause

The probe did not bind its output to the script. A weak model can edit the
shared client and the JSON. The check cannot see this drift.

## Decision

1. Preserve the deviated files as evidence. Do not use them.
2. Restore `call_load_client.py` to HEAD. HEAD matches the trusted FACT-0139
   method: one pre-connected set, drain before each repetition, warmups
   excluded.
3. Add `probe_sha256` and `client_sha256` to `gate.json`. Add a check for both.
4. Re-run B=224 and B=320. Use only warm rows.
5. Write a corrected run report. Mark attempt 1 as deviated in the new report.
6. Update IDEA-0008 and `facts.md` from the corrected report.

## Non-goals

- No app code change.
- No collector tuning.
- No commit.
