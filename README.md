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
- `.stageset/` — configuration, evidence, facts, reports, and session history.
- `scripts/` — StageSet status and validation tool.

The default code directory is `Code/`. Change it in `.stageset/config.yml` if required.

## Validation

```bash
python scripts/stageset-status.py
python scripts/stageset-status.py --sync
python scripts/stageset-status.py --validate
```

The status script uses only the Python standard library. GitHub Actions runs syntax and StageSet validation on pushes and pull requests.

See `STAGESET.md` for the complete protocol.
