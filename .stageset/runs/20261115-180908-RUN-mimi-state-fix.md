# Run report: Mimi decoder state fix

Run ID: 20261115-180908-RUN
Type: CHECK (audio quality defect)

## Problem
The FP32 and FP16 quality WAVs sounded compressed and dull. The defect was present in both paths.

## Cause
`Code/batch/batched_stream.py` did not advance the Mimi decoder state after each decode.
The decoder attention cache was overwritten at offset 0 on every frame. The decoder lost its past context.

## Change
Added `increment_steps(model.mimi, mimi_state, increment=mimi_steps)` after `decode_from_latent`.

## Evidence
- Before the fix, batched audio vs reference `generate_audio`: corr 0.6154.
- After the fix, batched audio vs reference `generate_audio`: corr 0.99999.
- Reference: 4.00 s, rms 0.0404, centroid 1169 Hz.
- Fixed batched: 3.84 s, rms 0.0413, centroid 1188 Hz.
- `Code/probes/check_batch_stream.py`: PASS.
- FP32 and FP16 WAVs regenerated in `Code/probes/out/fp16_quality/`. Metrics now match.

## Conclusion
The quality defect came from the missing Mimi state increment, not from FP16 or the language model.
A new manual listening check is required. The earlier listening gate is void.
