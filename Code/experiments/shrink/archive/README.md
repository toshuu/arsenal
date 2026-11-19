# Archived: Mimi swap experiment

Status: CLOSED. Negative result. Do not retry without a new dtype plan.

## Goal

Swap the multilingual Mimi decoder with a smaller English Mimi decoder to cut
steady decode time.

## Result

Both attempts failed on a dtype mismatch.

- First script `try_swap_mimi.py`: `Input type (torch.cuda.HalfTensor) and weight
  type (torch.cuda.FloatTensor) should be the same`.
- Second script `try_swap_mimi_fix.py`: `Input type (float) and bias type
  (c10::Half) should be the same`.

The FP16 backbone and the FP32 Mimi module do not share one dtype. FACT-0049
already shows that `.half()` on Mimi breaks the conv path.

## Files

- `try_swap_mimi.py`
- `try_swap_mimi_fix.py`
- `swap_mimi.json`
- `swap_mimi_fix.json`
- `swap_baseline.wav`
- `swapfix_baseline.wav`
- `swap_voice.pt`

## Decision

Keep the multilingual Mimi decoder. Do not retry the swap without a plan that
keeps one dtype across the encoder, decoder, and conv layers. The measured
steady split (FACT-0063) still puts Mimi at about 60% of the frame, so a future
decoder-only shrink needs a new approach.
