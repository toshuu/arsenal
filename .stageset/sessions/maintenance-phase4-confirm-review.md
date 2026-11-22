---
type: MAINTENANCE
time: 2026-11-22T19:57:37+05:30
summary: Review the real-server confirmation. B=320 is one batch but over 350 ms.
paths: .stageset/facts.md; .stageset/runs/20261122-195007-RUN.md; Ideas/IDEA-0008-natural-live-call-streaming.md
related: IDEA-0008; FACT-0154; SSLD-027; 20261122-195007-RUN
commit: -
remote: -
branch: -
---

# Session notes

## Decisions

- The B=320 split is a cap artifact. The cap of 640 removes it.
- The 350 ms gate is not met at B=320 on this T4. The measured floor is 389 to
  424 ms.
- The first-byte time includes the full 150 ms window wait. `target` was 640,
  so B<640 never reaches the target.
- Test one more formation policy: quiet grace, hard cap, buckets off. Use
  B=320 only. This removes the target wait.

## Outcomes

- Added FACT-0154 from `20261122-195007-RUN`.
- B=224 `sentence` is under 350 ms. B=224 `utterance` is borderline.

## Follow-up

- Write a real-server probe for B=320 with quiet grace, hard cap, and buckets
  off.
- If a policy passes, wire it. If none passes, report the floor and lock the
  operating point.
