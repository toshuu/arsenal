<!-- ss-living-doc v1 -->
# SSLD-005: Batched streaming core

## STATE
doc_id: SSLD-005
status: DONE
current_task: T005
tasks_done: 5
tasks_total: 5
skeleton: Skeletons/Code/batch/batched_stream.py
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-005-batch-stream.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-005-batch-stream.md --sync

## RULES
<!-- rules:start -->
1. Run `next_command` from STATE. It prints your one task. Work only on that task.
2. Do the steps in order. After each step, change `[ ]` to `[x]`.
3. Touch only the file in `file:` and the files in `also_edit:`. Never touch other files.
4. Copy code blocks exactly. Do not improve them. Do not rename anything.
5. After the last step, run the command in `verify:`. Compare the output to `expect:`.
6. If the output matches: paste the first output line into `result:`, set `status: DONE`, then run `sync_command`.
7. If the output does not match: do `if_fail:`, then run `verify:` again. Try at most 2 times.
8. If it still fails, or if anything is unclear: set `status: BLOCKED`, write the reason in `blocked_reason:`, run `sync_command`, then STOP. Do not guess.
9. Never edit this RULES block. Never add, delete, or reorder tasks. Never invent results.
10. After `sync_command`, run `next_command` again. When STATE shows `status: DONE`, STOP.
<!-- rules:end -->

## TASKS

### T001: Create package marker
status: DONE
blocked_reason:
file: Code/batch/__init__.py
context: Code/batch/ does not exist yet. This task creates the package marker for the new module.
do:
- [x] 1. CREATE `Code/batch/__init__.py` with the code block below.

   ```python
   """Batched streaming package."""
   ```
verify: `test -f Code/batch/__init__.py && echo OK`
expect: OK
if_fail: Create the directory `Code/batch/` and the file `Code/batch/__init__.py` with the code block. Run `verify:` again.
result: OK
### T002: Create the batched streaming module
status: DONE
blocked_reason:
file: Code/batch/batched_stream.py
context: This is the Phase B core. It runs one lockstep batch of unique texts on one GPU and streams each row.
do:
- [x] 1. CREATE `Code/batch/batched_stream.py` with the code block below.
- [x] 2. CHECK that the file has valid Python syntax.

   ```python
   """Batched streaming prototype for pocket-tts.

   One model copy, one process, one lockstep batch.
   This is Phase B of Ideas/optimization-strategy.md.
   """

   from __future__ import annotations

   import time
   from pathlib import Path
   from typing import Callable

   import torch

   from pocket_tts.data.audio import audio_read
   from pocket_tts.data.audio_utils import convert_audio, end_on_pause
   from pocket_tts.models.text_chunking import prepare_text_prompt, split_into_best_sentences
   from pocket_tts.modules.stateful_module import ModelState, init_states


   ChunkCallback = Callable[[int, torch.Tensor, float], None]


   def set_state_padding(model_state: ModelState, pad: torch.Tensor) -> None:
       for state in model_state.values():
           if isinstance(state, dict) and "pad" in state:
               state["pad"].copy_(pad.to(state["pad"].device))


   class BatchedStream:
       def __init__(self, model, voice_path: str | Path, max_tokens: int = 50):
           self.model = model
           self.device = next(model.flow_lm.parameters()).device
           self.max_tokens = max_tokens
           self.voice = self._load_voice(voice_path)

       def _load_voice(self, voice_path: str | Path) -> torch.Tensor:
           audio, sample_rate = audio_read(voice_path)
           audio = convert_audio(audio, sample_rate, self.model.config.mimi.sample_rate, 1)
           audio = end_on_pause(audio, self.model.config.mimi.sample_rate)
           with torch.no_grad():
               prompt = self.model._encode_audio(audio.unsqueeze(0).to(self.device))
           if self.model.flow_lm.insert_bos_before_voice:
               prompt = torch.cat([self.model.flow_lm.bos_before_voice, prompt], dim=1)
           return prompt

       def _first_chunk_text(self, text: str) -> str:
           chunks = split_into_best_sentences(
               self.model.flow_lm.conditioner.tokenizer,
               text,
               self.max_tokens,
               self.model.pad_with_spaces_for_short_inputs,
               self.model.remove_semicolons,
               self.model.append_terminal_punctuation,
               self.model.capitalize_first_letter,
               self.model.replace_characters,
           )
           return chunks[0] if chunks else text

       def _text_embedding(self, text: str) -> tuple[torch.Tensor, int]:
           prepared, _ = prepare_text_prompt(
               text,
               self.model.pad_with_spaces_for_short_inputs,
               self.model.remove_semicolons,
               self.model.append_terminal_punctuation,
               self.model.capitalize_first_letter,
               self.model.replace_characters,
           )
           tokens = self.model.flow_lm.conditioner.prepare(prepared)
           return self.model.flow_lm.conditioner(tokens), tokens.shape[1]

       def _build_prefixes(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
           rows = []
           token_counts = []
           for text in texts:
               first = self._first_chunk_text(text)
               text_emb, token_count = self._text_embedding(first)
               rows.append(torch.cat([self.voice, text_emb], dim=1)[0])
               token_counts.append(token_count)
           widths = [row.shape[0] for row in rows]
           width = max(widths)
           batch = torch.zeros(
               len(rows), width, rows[0].shape[-1], device=self.device, dtype=rows[0].dtype
           )
           pad = torch.zeros(len(rows), dtype=torch.long, device=self.device)
           for index, row in enumerate(rows):
               batch[index, width - row.shape[0] :] = row
               pad[index] = width - row.shape[0]
           return batch, pad, token_counts

       @torch.no_grad()
       def stream(
           self,
           texts: list[str],
           on_chunk: ChunkCallback | None = None,
           max_frames: int | None = None,
           frames_after_eos: int = 2,
       ) -> list[torch.Tensor]:
           model = self.model
           flow_lm = model.flow_lm
           batch_size = len(texts)
           device = self.device
           ldim = flow_lm.ldim
           dim = flow_lm.dim

           prefix, pad, token_counts = self._build_prefixes(texts)
           if max_frames is None:
               max_frames = min(128, max(model._estimate_max_gen_len(c) for c in token_counts) + 8)
           state = init_states(flow_lm, batch_size, prefix.shape[1] + max_frames + 2)
           set_state_padding(state, pad)

           mimi_steps = int(model.mimi.encoder_frame_rate / model.mimi.frame_rate)
           mimi_state = init_states(model.mimi, batch_size, (max_frames + 4) * mimi_steps)

           empty_tokens = torch.empty(batch_size, 0, dtype=torch.int64, device=device)
           empty_audio = torch.empty(batch_size, 0, dim, dtype=prefix.dtype, device=device)
           latent = flow_lm.bos_emb.view(1, 1, -1).expand(batch_size, 1, -1)
           audio_chunks: list[list[torch.Tensor]] = [[] for _ in range(batch_size)]
           countdown = torch.full((batch_size,), -1, dtype=torch.long, device=device)
           done = torch.zeros(batch_size, dtype=torch.bool, device=device)
           fade = torch.linspace(0, 1, model.config.mimi.sample_rate // 200, device=device)
           t0 = time.perf_counter()

           for step in range(max_frames):
               latent, is_eos = model._run_flow_lm_and_increment_step(
                   model_state=state,
                   text_tokens=empty_tokens,
                   backbone_input_latents=latent,
                   audio_conditioning=prefix if step == 0 else empty_audio,
               )
               eligible = torch.full_like(
                   countdown, step >= model._MIN_FRAMES_BEFORE_EOS, dtype=torch.bool
               )
               fired = is_eos.squeeze(-1).bool() & (countdown < 0) & eligible
               countdown = torch.where(
                   fired, torch.full_like(countdown, frames_after_eos), countdown
               )
               countdown = torch.where(countdown > 0, countdown - 1, countdown)
               now_done = countdown == 0

               decode_input = latent * flow_lm.emb_std + flow_lm.emb_mean
               audio = model.mimi.decode_from_latent(decode_input, mimi_state)
               frame = audio[:, 0]

               if step == 0:
                   fade_len = min(fade.numel(), frame.shape[-1])
                   frame[:, :fade_len] = frame[:, :fade_len] * fade[:fade_len]

               elapsed = time.perf_counter() - t0
               for row in range(batch_size):
                   if done[row]:
                       continue
                   if now_done[row]:
                       done[row] = True
                       continue
                   audio_chunks[row].append(frame[row].clone())
                   if on_chunk is not None:
                       on_chunk(row, frame[row], elapsed)

               if bool(done.all()):
                   break

           return [torch.cat(chunks) if chunks else torch.zeros(0, device=device) for chunks in audio_chunks]
   ```
verify: `python -m py_compile Code/batch/batched_stream.py && echo OK`
expect: OK
if_fail: Open `Code/batch/batched_stream.py`. Make it match the code block in step 2 exactly. Run `verify:` again.
result: OK
### T003: Create the smoke and parity check
status: DONE
blocked_reason:
file: Code/probes/check_batch_stream.py
context: The check compares a B=1 batch row with a B=3 batch row at temperature 0. It also checks first sound under 350 ms.
do:
- [x] 1. CREATE `Code/probes/check_batch_stream.py` with the code block below.
- [x] 2. CHECK that the file has valid Python syntax.

   ```python
   """Smoke check for Code/batch/batched_stream.py.

   Run from the repository root:
     python Code/probes/check_batch_stream.py

   It prints CHECK_BATCH_STREAM PASS on success and writes details to
   Code/probes/out/check_batch_stream.json.
   """

   import json
   import logging
   import os
   import sys
   from pathlib import Path

   import torch

   REPO = Path(__file__).resolve().parents[2]
   sys.path.insert(0, str(REPO / "Code"))
   os.chdir(REPO / "Code" / "model")

   logging.disable(logging.CRITICAL)
   from pocket_tts import TTSModel  # noqa: E402

   from batch.batched_stream import BatchedStream  # noqa: E402

   TEXTS = [
       "Hello, this is a short test sentence.",
       "Good morning. The weather is nice today.",
       "Testing one two three four five six seven eight nine ten.",
   ]


   def main() -> int:
       model = TTSModel.load_model(config="config.yaml").to("cuda").eval()
       stream = BatchedStream(model, REPO / "Code" / "probes" / "ref" / "voice.wav")

       model.temp = 0.0
       single = stream.stream([TEXTS[0]], max_frames=8)[0]
       batched = stream.stream(TEXTS, max_frames=8)
       diff = float((single - batched[0]).abs().max())

       model.temp = 0.3
       first = {}

       def on_chunk(row, chunk, elapsed):
           if row not in first and float(chunk.abs().max()) > 0.01:
               first[row] = elapsed

       stream.stream(TEXTS, on_chunk=on_chunk, max_frames=12)
       ok = diff < 1e-3 and len(first) == len(TEXTS) and max(first.values()) < 0.35

       out = {
           "parity_max_abs_diff": diff,
           "first_sound_ms": {str(k): round(v * 1000, 2) for k, v in sorted(first.items())},
           "result": "PASS" if ok else "FAIL",
       }
       path = REPO / "Code" / "probes" / "out" / "check_batch_stream.json"
       path.parent.mkdir(parents=True, exist_ok=True)
       path.write_text(json.dumps(out, indent=2) + "\n")
       print("CHECK_BATCH_STREAM PASS" if ok else "CHECK_BATCH_STREAM FAIL")
       return 0 if ok else 1


   if __name__ == "__main__":
       raise SystemExit(main())
   ```
verify: `python -m py_compile Code/probes/check_batch_stream.py && echo OK`
expect: OK
if_fail: Open `Code/probes/check_batch_stream.py`. Make it match the code block in step 2 exactly. Run `verify:` again.
result: OK
### T004: Run the smoke and parity check
status: DONE
blocked_reason:
file: Code/probes/check_batch_stream.py
context: This task runs the check on the T4. It writes Code/probes/out/check_batch_stream.json. It must print PASS.
do:
- [x] 1. RUN `python Code/probes/check_batch_stream.py`.
- [x] 2. CHECK that the command prints `CHECK_BATCH_STREAM PASS`.
- [x] 3. CHECK that `Code/probes/out/check_batch_stream.json` exists.
verify: `python Code/probes/check_batch_stream.py`
expect: CHECK_BATCH_STREAM PASS
if_fail: Read `Code/probes/out/check_batch_stream.json`. If parity is 1e-3 or more, compare the batch build in `_build_prefixes` with the skeleton. Run `verify:` again.
result: CHECK_BATCH_STREAM PASS
### T005: Update skeleton metadata
status: DONE
blocked_reason:
file: Skeletons/Batch/batched_stream.md
context: The code and checks are done. This task records that the skeleton implements spec_revision 1.
do:
- [x] 1. EDIT `Skeletons/Batch/batched_stream.md`: replace `status: READY` with `status: DONE`.
- [x] 2. EDIT `Skeletons/Batch/batched_stream.md`: replace `implemented_revision: 0` with `implemented_revision: 1`.
- [x] 3. EDIT `Skeletons/Batch/batched_stream.md`: replace `implemented_in: -` with `implemented_in: .stageset/sessions/coding-ssld-005-batch-stream.md`.
- [x] 4. EDIT `Skeletons/Batch/batched_stream.md`: replace `last_updated_in: .stageset/sessions/ideation-batch-server.md` with `last_updated_in: .stageset/sessions/coding-ssld-005-batch-stream.md`.
verify: `python -c "s=open('Skeletons/Batch/batched_stream.md').read(); print('OK' if all(x in s for x in ['implemented_revision: 1','status: DONE','implemented_in: .stageset/sessions/coding-ssld-005-batch-stream.md','last_updated_in: .stageset/sessions/coding-ssld-005-batch-stream.md']) else 'FAIL')"`
expect: OK
if_fail: Open `Skeletons/Batch/batched_stream.md`. Make the four replacements from steps 1 to 4. Run `verify:` again.
result: OK