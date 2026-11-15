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
from pocket_tts.modules.stateful_module import ModelState, increment_steps, init_states


ChunkCallback = Callable[[int, torch.Tensor, float], None]


def set_state_padding(model_state: ModelState, pad: torch.Tensor) -> None:
    for state in model_state.values():
        if isinstance(state, dict) and "pad" in state:
            state["pad"].copy_(pad.to(state["pad"].device))


class BatchedStream:
    def __init__(self, model, voice_path: str | Path, max_tokens: int = 50, voice_seconds: float | None = None, max_first_tokens: int | None = None):
        self.model = model
        self.device = next(model.flow_lm.parameters()).device
        self.max_tokens = max_tokens
        self.voice_seconds = voice_seconds
        self.max_first_tokens = max_first_tokens
        self.voice = self._load_voice(voice_path)

    def _load_voice(self, voice_path: str | Path) -> torch.Tensor:
        audio, sample_rate = audio_read(voice_path)
        audio = convert_audio(audio, sample_rate, self.model.config.mimi.sample_rate, 1)
        audio = end_on_pause(audio, self.model.config.mimi.sample_rate)
        if self.voice_seconds is not None:
            limit = int(self.voice_seconds * self.model.config.mimi.sample_rate)
            audio = audio[..., :limit]
        with torch.no_grad():
            prompt = self.model._encode_audio(audio.unsqueeze(0).to(self.device))
        if self.model.flow_lm.insert_bos_before_voice:
            prompt = torch.cat([self.model.flow_lm.bos_before_voice, prompt], dim=1)
        return prompt

    def _first_chunk_text(self, text: str) -> str:
        chunks = split_into_best_sentences(
            self.model.flow_lm.conditioner.tokenizer,
            text,
            self.max_first_tokens or self.max_tokens,
            self.model.pad_with_spaces_for_short_inputs,
            self.model.remove_semicolons,
            self.model.append_terminal_punctuation,
            self.model.capitalize_first_letter,
            self.model.replace_characters,
        )
        first = chunks[0] if chunks else text
        if self.max_first_tokens is None:
            return first
        tokenizer = self.model.flow_lm.conditioner.tokenizer
        ids = tokenizer(first)[0].tolist()
        if len(ids) <= self.max_first_tokens:
            return first
        return tokenizer.decode(ids[: self.max_first_tokens])

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
            increment_steps(model.mimi, mimi_state, increment=mimi_steps)
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
