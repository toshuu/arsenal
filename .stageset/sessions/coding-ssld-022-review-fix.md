---
type: CODING
time: 2026-11-22T14:28:10+05:30
summary: Review SSLD-022, fix the natural stream probe, and record Phase 0 evidence.
paths: Ideas/IDEA-0008-natural-live-call-streaming.md; Skeletons/Probes/probe_natural_stream.md; LivingDocs/SSLD-022-natural-live-call-streaming.md; Code/probes/probe_natural_stream.py; Code/probes/out/natural_stream/; .stageset/runs/20261122-142726-RUN.md; .stageset/facts.md
related: IDEA-0008; SSLD-022; 20261122-142726-RUN; FACT-0147
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- Keep the SSLD-022 evidence. The JSON files and WAV files are real.
- Use only warm repetitions for latency. The first repetition is cold and is
  about 1 s.
- Use `utterance` for low-load quality. Use `sentence` for high load. Keep
  `latency` for extreme load only.
- Add first-chunk size buckets for mixed text before the high-B server gate.
- Do not claim 100 ms for natural speech at B=64. Only the 16-token cut reached
  that level.
- Fix the probe. Resolve a relative `--out` path before `chdir`. Write WAVs next
  to the JSON. Report cold and warm values separately.

## Outcomes

- SSLD-022 is DONE: 6/6 tasks, 8 JSON files, 31 WAV files.
- Warm B=64 first-frame p95: `legacy` 97.26 ms, `sentence` 122.10 ms,
  `utterance` 181.31 ms for the same long text.
- Warm mixed B=64 first-frame p95: `sentence` 284.62 ms, `utterance`
  337.57 ms.
- Short rows end below 1 s in mixed batches. Long rows end at about 7.5 s.
  Compaction works, but late join is still missing.
- Added FACT-0147 and run report 20261122-142726-RUN.
- Updated IDEA-0008 with the Phase 0 result and the new implications.
- `Code/probes/probe_natural_stream.py` compiles after the path and warm-summary
  fix.

## Process gaps found

- The SSLD-022 coding run has no run reports and no coding event. The JSON and
  WAV evidence exists, but the per-check proof does not.
- The probe first wrote JSON under `Code/model/` because `--out` was relative
  and the code called `chdir` first. The files were moved by hand.
- The probe summary mixed the cold first repetition with warm repetitions. The
  first-frame values in the JSON summary are too high by about 1 s.

## Follow-up

- Run the owner listening gate on the `utterance` and `sentence` WAVs.
- Write the server mode plan. Add `utterance` and `sentence`. Turn off pause
  compression and fixed join for these modes.
- Add first-chunk size buckets. Measure mixed text again.
- Run Phase 2 at B=224 and B=448 on the server with short first chunks.
