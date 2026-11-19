<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/batched_stream.py
@stageset source_idea: IDEA-0003
@stageset status: DONE
@stageset priority: P0
@stageset spec_revision: 7
@stageset implemented_revision: 7
@stageset planned_in: .stageset/sessions/coding-ssld-013-ttfa-levers.md
@stageset last_updated_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset implemented_in: .stageset/sessions/coding-production-readiness-fixes.md
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: batched streaming core

## Purpose

Run one lockstep batch of unique texts through one model copy on one GPU.
Return the first non-silent audio for every row with low latency, and stream
the rest frame by frame.

This is Phase B of `Ideas/optimization-strategy.md`.

## Contract

Inputs:

- `model`: a loaded `TTSModel` on CUDA in eval mode.
- `voice_path`: path to one voice wav.
- `texts`: list of strings. Each text is split into chunks of at most `max_tokens`.
- `voice_seconds`: optional float. Truncate the voice prompt to this many
  seconds before encoding. Default `None` keeps the full voice.
- `max_first_tokens`: optional int. Cap the first text chunk at this token
  count. Default `None` uses `max_tokens`.
- `on_chunk(row, chunk, elapsed_s)`: optional callback.
- `max_frames`: optional frame cap. One frame is 80 ms.
- `frames_after_eos`: frames to add after EOS. Default 2.
- `on_stage(row, name, t)`: optional callback. `t` is an absolute
  `time.perf_counter()` value. `row` is `-1` for a batch-level event. The
  callback must stay cheap and must not synchronize the GPU. Stage names:
  - `stream_start`: the first line of `stream()`.
  - `prep_start`: just before text prep.
  - `prep_done`: after the text or prefix tensor is ready.
  - `state_done`: after the flow state is allocated and padded.
  - `cond_done`: after the conditioning forward.
  - `flow0_done`: after the step 0 flow forward.
  - `mimi0_done`: after the step 0 Mimi decode.
  - `first_emit`: for each row when its first audio chunk is appended.

Outputs:

- A list of 1-D float tensors, one per row. Each tensor is the streamed audio.
- Side effect: calls `on_chunk` for every emitted frame with the row index,
  the audio chunk, and the elapsed time in seconds since the first step.

Rules:

- One process, one model, one batch. No threads.
- Prefix order is `[BOS, voice, text]`.
- Rows are right-aligned. `pad` is set on the flow state.
- The first step includes the prefix and the BOS latent in one forward.
- The decoder is batched. One `decode_from_latent` call per frame.
- After each decode, advance the Mimi state by `mimi_steps`. The value is
  `mimi.encoder_frame_rate / mimi.frame_rate`. The reference path does this.
  Without it, the decoder cache is overwritten at offset 0 and audio is dull.
- The first audio frame gets a 5 ms fade-in.
- `voice_seconds` truncates the prompt after resampling, then calls
  `end_on_pause` on the cut audio, then encodes. The prompt must end on a pause.
- `max_first_tokens` overrides `max_tokens` for the first text chunk only.
- A row stops at its own EOS. The batch stops when all rows stop or hit the cap.
- Revision 6 adds two performance contracts:
  - Text prep: tokenize all texts with one pool of workers and one batched
    embedding call. Use a per-text id cache. Do not run one GPU op per row.
  - Emit path: append a view of the decoded frame. Do not clone each row.
    Keep a `row_ids` map through compaction. No per-row `.item()` or `.cpu()`.
  - The decoded audio returns as float32.

## Structure

- `set_state_padding(model_state, pad)`: copy the per-row pad into every state dict
  that has a `pad` key.
- `BatchedStream`:
  - `__init__(model, voice_path, max_tokens=50, voice_seconds=None, max_first_tokens=None)`: cache the voice prefix.
  - `_load_voice(voice_path)`: read, resample, trim, encode, add BOS. Truncate
    to `voice_seconds` when set.
  - `_first_chunk_text(text)`: return the first text chunk. Use
    `max_first_tokens` when set.
  - `_text_embedding(text)`: prepare text, tokenize, embed. Return the embedding
    and the token count.
  - `_build_prefixes(texts)`: build a right-aligned prefix tensor, a pad tensor,
    and the token counts.
  - `stream(texts, on_chunk=None, max_frames=None, frames_after_eos=2, on_stage=None)`:
    run the batch and return the audio per row.
- `_text_ids(text)`: return cached token ids for one text.
- `_encode_texts(texts)`: one batched embedding call. Right-align rows and zero
  the leading pad positions. Return the batch, pad, and token counts.
- `mark(row, name)`: emit one stage timestamp through `on_stage` when it is set.
  It uses `time.perf_counter()`. It must not call any CUDA sync.

## Pseudo-code

1. Build the voice prefix once. It is `[BOS, voice]`. Apply `voice_seconds` first.
2. For each text, take the first chunk, prepare it, embed it, and append it to
   the voice prefix. Record the row width.
3. Right-align all rows to the widest prefix. Record `pad = width - row_width`.
4. Allocate the flow state and the Mimi state for batch size B.
5. Set `pad` on the flow state.
6. Set the first latent to `bos_emb` for every row.
7. For each frame:
   - Run `_run_flow_lm_and_increment_step` with the prefix on step 0.
   - Update the per-row EOS countdown.
   - Scale the latent by `emb_std` and `emb_mean`.
   - Decode the whole batch with `mimi.decode_from_latent`.
   - Advance the Mimi state by `mimi_steps` with `increment_steps`.
   - Apply the first-frame fade-in.
   - Emit only rows that are not done. Call `on_chunk`.
   - Stop when every row is done or `max_frames` is reached.
8. Return the concatenated audio per row.

## Assumptions

ASSUMPTION: A-09 - `_run_flow_lm_and_increment_step` accepts batch B and returns a latent `[B,1,ldim]` and `is_eos` `[B,1]`. [UNVERIFIED]
ASSUMPTION: A-10 - `mimi.decode_from_latent` accepts `[B,T,C]` with a batched `mimi_state`. [UNVERIFIED]
ASSUMPTION: A-11 - The `pad` field masks left padding and makes a ragged batch match a B=1 batch. [UNVERIFIED]
ASSUMPTION: A-12 - `split_into_best_sentences` returns one chunk for a text of at most 50 tokens. [UNVERIFIED]

## Edge cases

- B=1: `pad` is zero. Output must match a B=3 batch row within 1e-3 at temperature 0.
- Empty text: raise `ValueError` before the first step.
- Text longer than one chunk: every chunk is generated in order. No word is dropped.
- Early EOS: a row stops after `frames_after_eos`. Other rows continue.
- High B: raise a clear `RuntimeError` when CUDA runs out of memory.
- Over-limit frames: raise `ValueError` before state allocation.
- Frame budget reached before EOS: raise `RuntimeError` when `max_frames` was not set. Set `last_truncated_rows`.
- Different text lengths: the padding must not change any row output.

## Checks

### CHECK-BATCH-STREAM-01 - smoke and parity

- Command: `python Code/probes/check_batch_stream.py`
- Predicted output: `CHECK_BATCH_STREAM PASS`
- Pass condition: exit code 0 and the exact line `CHECK_BATCH_STREAM PASS`.
- Fail condition: any other output or a non-zero exit code.

### CHECK-BATCH-STREAM-02 - parity value

- Command: `python -c "import json; d=json.load(open('Code/probes/out/check_batch_stream.json')); print(d['parity_max_abs_diff'] < 1e-3)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the file is missing or the value is 1e-3 or more.

### CHECK-BATCH-STREAM-05 - cut before pause

- Command: `python Code/probes/check_voice_cut_order.py`
- Predicted output: `CHECK_VOICE_CUT_ORDER PASS`
- Pass condition: exit code 0 and the line `CHECK_VOICE_CUT_ORDER PASS`.
- Fail condition: any other output or a non-zero exit code. The check proves that `_load_voice` cuts the audio before it calls `end_on_pause`.

### CHECK-BATCH-STREAM-04 - lever knobs

- Command: `python Code/probes/check_batch_levers.py`
- Predicted output: `CHECK_BATCH_LEVERS PASS`
- Pass condition: exit code 0 and the line `CHECK_BATCH_LEVERS PASS`.
- Fail condition: any other output or a non-zero exit code. The check confirms that `voice_seconds` shortens the prefix and `max_first_tokens` shortens the first chunk.

### CHECK-BATCH-STREAM-03 - decoder state parity

- Command: `python Code/probes/cmp_reference_audio.py`
- Predicted output: `DECODER PARITY PASS`
- Pass condition: exit code 0 and the line `DECODER PARITY PASS`.
- Fail condition: any other output or a non-zero exit code. If the correlation is below 0.99, the Mimi state increment is missing.

### CHECK-BATCH-STREAM-06 - stage timestamps

- Command: `python -c "import re; s=open('Code/batch/batched_stream.py').read(); print(bool(re.search(r'on_stage: StageCallback', s)))"`
- Predicted output: `True`
- Pass condition: the command prints `True`. The probe run report must also
  show all eight stage names in order for one row.
- Fail condition: `on_stage` is absent from the signature, or a stage name is
  missing in the probe output.

### CHECK-BATCH-STREAM-07 - prep under 10 ms

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_maxb.json')); print(d['stages']['128']['prep_ms']['p50'] < 10)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the B=128 text-prep p50 is 10 ms or more.

### CHECK-BATCH-STREAM-08 - emit under 5 ms

- Command: `python -c "import json; d=json.load(open('Code/probes/out/probe_ttfa_maxb.json')); print(d['stages']['128']['emit_ms']['p50'] < 5)"`
- Predicted output: `True`
- Pass condition: the command prints `True`.
- Fail condition: the B=128 emit p50 is 5 ms or more.

### CHECK-BATCH-STREAM-09 - parity regression

- Command: `python Code/probes/check_batch_stream.py`
- Predicted output: `CHECK_BATCH_STREAM PASS`
- Pass condition: exit code 0 and the exact line `CHECK_BATCH_STREAM PASS`.
- Fail condition: any other output or a non-zero exit code.

### CHECK-BATCH-STREAM-10 - full text coverage

- Command: `PYTHONPATH=/kaggle/working/pocket-tts python Code/probes/check_long_text.py`
- Predicted output: `{"ok": true, "chunks": 2}`
- Pass condition: exit code 0 and `coverage_ok` is true. No word is missing.
- Fail condition: any missing word, or any other output.

### CHECK-BATCH-STREAM-11 - frame guard

- Command: `PYTHONPATH=/kaggle/working/pocket-tts python Code/probes/check_long_text.py`
- Predicted output: `{"ok": true, "chunks": 2}`
- Pass condition: exit code 0 and `guard_ok` and `chunk_guard_ok` are true.
- Fail condition: the guard does not raise `ValueError` before allocation.

### CHECK-BATCH-STREAM-12 - no silent truncation

- Command: `PYTHONPATH=/kaggle/working/pocket-tts python Code/probes/check_long_text.py`
- Predicted output: `{"ok": true, "chunks": 2}`
- Pass condition: exit code 0, `longer_than_first` is true, and `explicit_truncation_rows` is not empty.
- Fail condition: the full text is not longer than the first chunk, or the truncation rows are not recorded.

## References

- `Ideas/optimization-strategy.md`
- `Ideas/IDEA-0004-ttfa-burst-gain.md`
- `Ideas/high-concurrency-burst-optimization.md`
- `training/modules/model.py` (`generate`, the ragged batch reference)
- `pocket_tts/models/tts_model.py` (`_run_flow_lm_and_increment_step`, `_encode_audio`)
- `pocket_tts/modules/attention.py` (`pad`, `complete_kv`)
- `Code/probes/check_batch_stream.py`
