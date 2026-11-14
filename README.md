# Arsenal

Feather but p-ed.

This repository uses the StageSet planning and implementation workflow.

## Start here

1. Read `.stageset/DIGEST.md`.
2. Read `.stageset/config.yml`.
3. Read `STAGESET.md` for the full workflow.
4. Read `CHATGPT.md` before planning with ChatGPT.
5. Read `ideations-rules.md` before planning.
6. Read `coder-rules.md` before coding.
7. Use `PLANNER-START.md` to start a planning session.
8. Run `python scripts/stageset-status.py` to see ready work.

## Workspace

- `Ideas/` — requirements, decisions, risks, and open questions.
- `Skeletons/` — file-level implementation blueprints and probes.
- `Code/` — actual source code.
- `LivingDocs/` — ss-living-doc files for weak coding models.
- `viewer/` — static status viewer.
- `.stageset/` — configuration, evidence, facts, reports, and session history.
- `scripts/` — StageSet status, report, and ss-living-doc tools.

The default code directory is `Code/`. Change it in `.stageset/config.yml` if required.

## Validation

```bash
python scripts/stageset-status.py
python scripts/stageset-status.py --sync
python scripts/stageset-status.py --validate
python scripts/stageset-report.py
python scripts/ss-living-doc.py LivingDocs/SSLD-001-x.md
```

The status script uses only the Python standard library. GitHub Actions runs syntax, report, ss-living-doc, and StageSet validation on pushes and pull requests.

## Status viewer

Make the report after each session:

```bash
python scripts/stageset-report.py
git add .stageset/report.json && git commit -m "Update report" && git push
```

Open the StageSet viewer and add `toshuu/arsenal`. See `.stageset/report-format.md`.

## ss-living-doc

An **ss-living-doc** is a step list for a weak coding model. The name means **StageSet living document**. Files live in `LivingDocs/`. See `.stageset/ss-living-doc-format.md`.

Do not confuse it with a run report. A run report is evidence in `.stageset/runs/`. An ss-living-doc is a plan in `LivingDocs/`.

```bash
python scripts/ss-living-doc.py LivingDocs/SSLD-001-x.md
python scripts/ss-living-doc.py LivingDocs/SSLD-001-x.md --next
python scripts/ss-living-doc.py LivingDocs/SSLD-001-x.md --sync
```

See `STAGESET.md` for the complete protocol.
