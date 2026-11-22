<!--
@stageset version: 2
@stageset kind: PROBE
@stageset target: -
@stageset source_idea: IDEA-0008
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/maintenance-phase4-quiet-review.md
@stageset last_updated_in: .stageset/sessions/maintenance-phase4-quiet-review.md
@stageset implemented_in: .stageset/sessions/coding-phase4-quiet-fix.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Probe: Phase 4 quiet early-break fix

## Goal

Test if the quiet early-break guard removes the `[1,319]` split at B=320.

## Method

- Real uvicorn. Fresh server per policy.
- Cap 640, window 150 ms, buckets off, quiet 2 or 3, hard 30 or 40.
- B=320 only. `sentence` and `utterance`. 6 calls. Warm = call 2 to 5.
- Save `Code/probes/out/phase4_quiet_fix/fix.json`.

## Decision rule

- PASS if any policy has all warm rows `[320]` and worst warm p95 <= 350 ms.
- FAIL if no policy passes. Report floor.

## Checks

### CHECK-QUIET-FIX-01
- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_quiet_fix/fix.json')); print(len(d['rows']), len(d['policies']))"`
- Pass condition: `24 2`

### CHECK-QUIET-FIX-02
- Command: `python -c "import json; d=json.load(open('Code/probes/out/phase4_quiet_fix/fix.json')); rows=d['rows']; out={}; [out.setdefault(p['name'],[]).append(r) for p in d['policies'] for r in rows if r['policy']==p['name'] and r['warm']]; print({k:(all(r['batch_sizes']==[320] for r in v), max(r['p95'] for r in v)) for k,v in out.items()})"`
- Pass condition: one policy has `(True, <=350)`.

## References

- `Code/batch/server.py`
- `.stageset/runs/20261122-195737-RUN.md`
