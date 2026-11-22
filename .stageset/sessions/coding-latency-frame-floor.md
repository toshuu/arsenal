---
type: CODING
time: 2026-11-22T19:05:33+00:00
summary: Lower the WS latency frame floor to 8 and fit word jobs to the cap.
paths: Code/batch/server.py; Code/probes/web_latency/index.html
related: IDEA-0008; 20261122-235919-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Change

- `Code/batch/server.py` now uses `ARSENAL_LATENCY_MIN_FRAMES` with default 8
  for `latency` mode. `sentence` and `utterance` keep the 24-frame floor.
- The web page allows caps from 8 to 192.
- The page derives words per job from the cap with the measured estimate
  `25 + 7.5 * (n - 1)`. This stops cap hits at 24 and above.

## Result

- Cap 24: 21 single-word jobs, no cap hit, all EOS, 12.64 s audio.
- Cap 56: 5 jobs, no cap hit, all EOS, 8.04 s audio.
- Caps 8 and 16 can cut a word because one word can need more than 8 or 16
  frames. The page warns that the cap is a ceiling.

## Non-goal

No change to `sentence` mode or quality caps. No commit.
