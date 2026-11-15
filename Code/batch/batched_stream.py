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


def _clone_state_to_batch(
    state: ModelState, batch_size: int, sequence_length: int, device: torch.device
) -> ModelState:
    out: ModelState = {}
    for name, module_state in state.items():
        new_state: dict[str, torch.Tensor] = {}
        for key, value in module_state.items():
            if key == "cache":
                expanded = torch.full(
                    (value.shape[0], batch_size, sequence_length, value.shape[3], value.shape[4]),
                    float("NaN"),
                    device=device,
                    dtype=value.dtype,
                )
                expanded[:, :, : value.shape[2], :, :] = value.expand(-1, batch_size, -1, -1, -1)
                new_state[key] = expanded
            elif key in ("offset", "pad"):
                new_state[key] = value.expand(batch_size).clone().to(device)
            else:
                if value.dim() > 0 and value.shape[0] == 1:
                    new_state[key] = value.expand(batch_size, *value.shape[1:]).clone().to(device)
                else:
                    new_state[key] = value.clone().to(device)
        out[name] = new_state
    return out


def _slice_model_state(state: ModelState, keep: torch.Tensor, cur_batch: int) -> ModelState:
    out: ModelState = {}
    for name, module_state in state.items():
        new_state: dict[str, torch.Tensor] = {}
        for key, value in module_state.items():
            if key == "cache":
                new_state[key] = value.index_select(1, keep).contiguous()
            elif key in ("offset", "pad"):
                new_state[key] = value.index_select(0, keep).contiguous()
            elif torch.is_tensor(value) and value.dim() > 0 and value.shape[0] == cur_batch:
                new_state[key] = value.index_select(0, keep).contiguous()
            else:
                new_state[key] = value
        out[name] = new_state
    return out


class BatchedStream:
    def __init__(
        self,
        model,
        voice: str | Path | None = None,
        max_tokens: int = 50,
        voice_seconds: float | None = None,
        max_first_tokens: int | None = None,
        voice_profile: str | Path | None = None,
        decode_group: int = 1,
        compact: bool = True,
    ):
        self.model = model
        self.device = next(model.flow_lm.parameters()).device
        self.max_tokens = max_tokens
        self.voice_seconds = voice_seconds
        self.max_first_tokens = max_first_tokens
        self.decode_group = max(1, int(decode_group))
        self.compact = compact
        self.voice: torch.Tensor | None = None
        self.voice_state: ModelState | None = None
        if voice_profile is not None:
            self._load_voice_profile(voice_profile)
        elif voice is not None:
            self.voice = self._load_voice(voice)
        else:
            raise ValueError("voice or voice_profile is required")

    @torch.no_grad()
    def _load_voice(self, voice_path: str | Path) -> torch.Tensor:
        audio, sample_rate = audio_read(voice_path)
        audio = convert_audio(audio, sample_rate, self.model.config.mimi.sample_rate, 1)
        if self.voice_seconds is not None:
            limit = int(self.voice_seconds * self.model.config.mimi.sample_rate)
            audio = audio[..., :limit]
        audio = end_on_pause(audio, self.model.config.mimi.sample_rate)
        with torch.no_grad():
            prompt = self.model._encode_audio(audio.unsqueeze(0).to(self.device))
        if self.model.flow_lm.insert_bos_before_voice:
            prompt = torch.cat([self.model.flow_lm.bos_before_voice, prompt], dim=1)
        return prompt

    @torch.no_grad()
    def _load_voice_profile(self, profile_path: str | Path) -> None:
        data = torch.load(profile_path, map_location=self.device)
        self.voice = data["voice_emb"].to(self.device)
        self.voice_seconds = data.get("voice_seconds", self.voice_seconds)
        state = data.get("voice_state")
        if state is not None:
            self.voice_state = {
                name: {k: v.to(self.device) for k, v in module.items()} for name, module in state.items()
            }

    @torch.no_grad()
    def save_voice_profile(self, profile_path: str | Path, conditioned: bool = False) -> None:
        if self.voice is None:
            raise ValueError("no voice to save")
        data = {"voice_emb": self.voice.detach().cpu(), "voice_seconds": self.voice_seconds}
        if conditioned:
            if self.voice_state is not None:
                state = self.voice_state
            else:
                state = init_states(self.model.flow_lm, 1, self.voice.shape[1])
                self.model._run_flow_lm_and_increment_step(model_state=state, audio_conditioning=self.voice)
            data["voice_state"] = {
                name: {k: v.detach().cpu() for k, v in module.items()} for name, module in state.items()
            }
        Path(profile_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(data, profile_path)

    def _voice_state_len(self) -> int:
        if self.voice_state is None:
            return 0
        for module_state in self.voice_state.values():
            offset = module_state.get("offset")
            if offset is not None:
                return int(offset.view(-1)[0].item())
        return self.voice.shape[1] if self.voice is not None else 0

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

    def _build_text_batch(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
        rows = []
        token_counts = []
        for text in texts:
            first = self._first_chunk_text(text)
            text_emb, token_count = self._text_embedding(first)
            rows.append(text_emb[0])
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
        dim = flow_lm.dim

        use_profile_state = self.voice_state is not None
        if use_profile_state:
            text_batch, text_pad, token_counts = self._build_text_batch(texts)
            if max_frames is None:
                max_frames = min(128, max(model._estimate_max_gen_len(c) for c in token_counts) + 8)
            vlen = self._voice_state_len()
            seq_len = vlen + text_batch.shape[1] + max_frames + 4
            state = _clone_state_to_batch(self.voice_state, batch_size, seq_len, device)
            set_state_padding(state, text_pad)
            empty_tokens = torch.empty(batch_size, 0, dtype=torch.int64, device=device)
            empty_latents = torch.empty(batch_size, 0, flow_lm.ldim, dtype=text_batch.dtype, device=device)
            empty_audio = torch.empty(batch_size, 0, dim, dtype=text_batch.dtype, device=device)
            model._run_flow_lm_and_increment_step(
                model_state=state,
                text_tokens=empty_tokens,
                backbone_input_latents=empty_latents,
                audio_conditioning=text_batch,
            )
            prefix = None
        else:
            prefix, pad, token_counts = self._build_prefixes(texts)
            if max_frames is None:
                max_frames = min(128, max(model._estimate_max_gen_len(c) for c in token_counts) + 8)
            state = init_states(flow_lm, batch_size, prefix.shape[1] + max_frames + 2)
            set_state_padding(state, pad)
            empty_tokens = torch.empty(batch_size, 0, dtype=torch.int64, device=device)
            empty_audio = torch.empty(batch_size, 0, dim, dtype=prefix.dtype, device=device)

        mimi_steps = int(model.mimi.encoder_frame_rate / model.mimi.frame_rate)
        mimi_state = init_states(model.mimi, batch_size, (max_frames + 4) * mimi_steps)

        latent = flow_lm.bos_emb.view(1, 1, -1).expand(batch_size, 1, -1)
        audio_chunks: list[list[torch.Tensor]] = [[] for _ in range(batch_size)]
        countdown = torch.full((batch_size,), -1, dtype=torch.long, device=device)
        done = torch.zeros(batch_size, dtype=torch.bool, device=device)
        fade = torch.linspace(0, 1, model.config.mimi.sample_rate // 200, device=device)
        t0 = time.perf_counter()

        pending: list[tuple[torch.Tensor, torch.Tensor, int]] = []

        def flush_pending(force: bool = False) -> bool:
            nonlocal done
            if not pending:
                return bool(done.all())
            if not force and len(pending) < self.decode_group:
                return False
            latents = torch.cat([p[0] for p in pending], dim=1)
            decode_input = latents * flow_lm.emb_std + flow_lm.emb_mean
            audio = model.mimi.decode_from_latent(decode_input, mimi_state)
            increment_steps(model.mimi, mimi_state, increment=mimi_steps * len(pending))
            # audio: [B, 1, T*samples_per_frame] or [B, T*samples_per_frame]
            if audio.dim() == 3:
                audio = audio[:, 0]
            frame_samples = audio.shape[-1] // len(pending)
            frames = audio.view(batch_size, len(pending), frame_samples)
            elapsed = time.perf_counter() - t0
            for i, (_, nd, stp) in enumerate(pending):
                frame = frames[:, i]
                if stp == 0:
                    fade_len = min(fade.numel(), frame.shape[-1])
                    frame[:, :fade_len] = frame[:, :fade_len] * fade[:fade_len]
                for row in range(batch_size):
                    if done[row]:
                        continue
                    if bool(nd[row]):
                        done[row] = True
                        continue
                    audio_chunks[row].append(frame[row].clone())
                    if on_chunk is not None:
                        on_chunk(row, frame[row], elapsed)
            pending.clear()
            return bool(done.all())

        for step in range(max_frames):
            if step == 0:
                conditioning = step0_cond if "step0_cond" in locals() else (empty_audio if use_profile_state else prefix)
            else:
                conditioning = empty_audio
            latent, is_eos = model._run_flow_lm_and_increment_step(
                model_state=state,
                text_tokens=empty_tokens,
                backbone_input_latents=latent,
                audio_conditioning=conditioning,
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

            pending.append((latent, now_done.clone(), step))
            force = step == 0 or bool(now_done.any())
            if flush_pending(force=force):
                break

            if self.compact and bool(now_done.any()) and not bool(done.all()):
                keep = (~done).nonzero(as_tuple=False).squeeze(-1)
                if keep.numel() > 0 and keep.numel() < batch_size:
                    keep_cpu = keep.detach().cpu()
                    for local, orig in enumerate(keep_cpu.tolist()):
                        if local != orig:
                            audio_chunks[orig] = audio_chunks[local]
                    # truncate moved-from slots (optional)
                    state = _slice_model_state(state, keep, batch_size)
                    mimi_state = _slice_model_state(mimi_state, keep, batch_size)
                    latent = latent.index_select(0, keep).contiguous()
                    countdown = countdown.index_select(0, keep).contiguous()
                    done = done.index_select(0, keep).contiguous()
                    empty_tokens = empty_tokens.index_select(0, keep).contiguous() if empty_tokens.dim() > 0 else torch.empty(keep.numel(), 0, dtype=torch.int64, device=device)
                    empty_audio = empty_audio.index_select(0, keep).contiguous()
                    batch_size = keep.numel()

        flush_pending(force=True)

        return [torch.cat(chunks) if chunks else torch.zeros(0, device=device) for chunks in audio_chunks]
