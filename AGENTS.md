# Instructions for coding agents

This workspace uses StageSet. Before you inspect or change project code, read:

1. `.stageset/DIGEST.md`.
2. `.stageset/facts.md`.
3. `STAGESET.md`.
4. `.stageset/config.yml`.
5. `coder-rules.md`.
6. `.stageset/sessions-tracker.md`.
7. Open blockers and their run reports.
8. `.stageset/ss-living-doc-format.md` when an ss-living-doc is assigned.

## ss-living-doc

An **ss-living-doc** is a step list for a weak coding model. It lives in `LivingDocs/`. It is not a run report.

When an ss-living-doc is assigned:

1. Run its `next_command`. It prints one task only.
2. Do only that task.
3. Change `[ ]` to `[x]` after each step.
4. Run `verify:` and compare the output to `expect:`.
5. Write the real output in `result:`. Set `status: DONE`.
6. Run `sync_command`. Then run `next_command` again.
7. If it fails twice, set `status: BLOCKED`, write `blocked_reason:`, run `sync_command`, and STOP.

Never edit STATE by hand. Never change the RULES block. Never invent output. Read `.stageset/ss-living-doc-format.md` for the full format.

Run `python scripts/stageset-status.py` to find ready skeletons. Read each full skeleton and its linked idea files before you implement it.

Follow the skeleton and its checks. Verify every `ASSUMPTION:` before you rely on it. Generate a timestamp-based run ID with `python scripts/stageset-status.py --new-run-id`. Save one run report for each check attempt. Keep observed facts separate from guesses.

Stop after three failed attempts for one check. Set the skeleton to `BLOCKED`, set `blocker_ref` to the third run report, and create an escalation file with `--escalate CHECK-ID`. Do not redesign the feature. If a required skeleton step is impossible, do not deviate silently. Set the skeleton to `BLOCKED` and link a run report that records the conflict.

After each focused coding session, create one event file in `.stageset/sessions/`. Run `python scripts/stageset-status.py --sync` and then `python scripts/stageset-status.py --validate`. Do not edit the generated tracker or digest by hand.

Record a `PUSH` event only after a remote push succeeds. Use ASD-STE100-style English in project documents, comments, run reports, and event summaries.
