# Run report: manual listening gate

Run ID: 20261115-181309-RUN
Type: CHECK (quality gate)

## Checks
- Owner listened to all nine WAVs in `Code/probes/out/fp16_quality/`.
- Language content is correct in EN, HI, and MR.
- Audio quality is correct in FP32 and FP16.
- The compressed and dull sound from the earlier run is gone.

## Result
PASS.

## Notes
- The earlier gate failed because `BatchedStream` did not advance the Mimi decoder state (FACT-0015).
- The fix is confirmed by listening. FP16 has no audible quality loss against FP32 in these clips.

## Conclusion
The FP16 quality gate passes. Phase C is unblocked.
