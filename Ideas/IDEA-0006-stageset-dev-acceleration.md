---
id: IDEA-0006
title: StageSet system acceleration for project dev
status: DISCOVERY
priority: P1
created_in: .stageset/sessions/coding-b224-ramp.md
updated_in: .stageset/sessions/coding-modal-t4-deploy.md
---

# IDEA-0006: StageSet system acceleration for project dev

- Status: DRAFT
- Date: 2026-11-20
- Scope: StageSet workflow/tooling improvements to increase evidence throughput and reduce iteration time (motivated by HTTP B=224 first-chunk cliff diagnosis, FACT-0117).

## Goal

Make experiments, decisions, and handoffs faster and more reliable so the project reaches gate targets (e.g. HTTP p95 ≤ 350 ms at max B) with fewer repeated/manual steps.

## Proposed changes (priority order)

### 1. Auto-ingest probe results → facts/runs
**Problem:** Probe outputs (`tl_*`, `timeline_*`, diag JSONs) are manually translated into FACTs/run docs; slow and error-prone.

**Proposal**
- Standardize probe result schema: `config` (B, window, pinning, threads, profile, host), `git_sha`, `env`, `metrics` (`srv_p50/p95`, `cli_p50/p95`, `q_p50/p95`, `errors`, `rtf`, `per-stage p50/p95`), `gate_pass`, `artifacts`.
- Add `stageset ingest <result.json>` to: create/update a run report entry, append/draft a FACT with numbers and artifact links, and record config.

**Impact:** Evidence captured in one step; consistent records; faster diagnosis cycles.

### 2. Gate & baseline registry in config/report
**Problem:** Gates/baselines live across facts/docs (direct B=224 FACT-0064/0087/0111, HTTP32/224, dislike baseline FACT-0109); regressions hard to spot quickly.

**Proposal**
- Define gates in config: e.g. direct B=224 p95, HTTP 32-client p95≤350, HTTP 224-client p95≤350, RTF<1, “max stable B”, with baseline references.
- `stageset-report` outputs a gate table (PASS/FAIL/OPEN), current vs baseline delta, and regression flags.

**Impact:** Immediate “where we stand / chance of target”; early detection of regressions (e.g. FACT-0113).

### 3. Lever/decision ledger (hypothesis → evidence → decision)
**Problem:** Tried levers and outcomes (kept/dropped/no-go) are scattered, risking re-runs.

**Proposal**
- Structured ledger per lever: `hypothesis`, `change/config`, `result metrics`, `decision` (`keep`/`drop`/`no-go`/`blocked`), `reason`, `evidence` links.
- Examples to encode: timeline gated `ARSENAL_TIMELINE` kept; unpinned/torch_threads unsafe (B32/37 regress/unstable); Step 3 continuous batching NO-GO on 4-vCPU host (FACT-0117).

**Impact:** Preserves learnings across sessions/agents; avoids repeating dead ends.

### 4. One-command handoff snapshot
**Problem:** Resuming requires reconstructing context from DIGEST/facts/sessions/skeletons.

**Proposal**
- `stageset handoff` generates: objective, gate table, max stable B, blockers/root cause, next 3 levers, key files/artifacts, and commit hash.

**Impact:** Near-zero ramp-up for next session or agent.

### 5. Artifact index + integrity validation
**Problem:** Numbers in docs must be traceable to files/commits; links can drift.

**Proposal**
- Require each FACT/run to reference artifact paths and commit.
- Extend `--validate` to check referenced artifacts exist and (optionally) key metrics match source JSON fields.

**Impact:** Trustworthy, navigable evidence; fast “where did this p95 come from?” answers.

### 6. Reproducible sweep/matrix runner
**Problem:** Ramps/sweeps (B × window × pinning × threads) are ad-hoc and hard to compare.

**Proposal**
- Declarative matrix spec, deterministic output naming, skip-completed cells, aggregated comparison table, and ingest-compatible result files.

**Impact:** Systematic, comparable searches with less manual orchestration.

## Suggested rollout
1. **(1) Ingest + schema** — highest leverage on documentation/diagnosis time.
2. **(2) Gates/baselines + (5) validation** — correctness and regression safety.
3. **(4) Handoff + (3) ledger** — continuity and decision memory.
4. **(6) Matrix runner** — scale experiments once evidence pipeline is solid.

## Success metrics
- Time from probe completion to recorded FACT/run: minutes (target <5) vs manual.
- Zero missing/broken evidence links in `--validate`.
- Regressions flagged automatically against baseline gates.
- Handoff sufficient to resume without re-reading full history.
