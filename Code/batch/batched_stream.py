"""Batched streaming prototype for pocket-tts.

One model copy, one process, one lockstep batch.
This is Phase B of Ideas/optimization-strategy.md.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import torch

from pocket_tts.data.audio import audio_read
from pocket_tts.data.audio_utils import convert_audio, end_on_pause
from pocket_tts.models.text_chunking import prepare_text_prompt, split_into_best_sentences
from pocket_tts.modules.stateful_module import ModelState, increment_steps, init_states
from .overlap import OverlapDecoder


ChunkCallback = Callable[[int, torch.Tensor, float], None]
StageCallback = Callable[[int, str, float], None]


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
        overlap_decode: bool = False,
    ):
        self.model = model
        self.device = next(model.flow_lm.parameters()).device
        self.max_tokens = max_tokens
        self.voice_seconds = voice_seconds
        self.max_first_tokens = max_first_tokens
        self.decode_group = max(1, int(decode_group))
        self.compact = compact
        self.overlap = OverlapDecoder(self.device) if overlap_decode else None
        self._inflight = None
        self._ids_cache: dict[str, list[int]] = {}
        self._pool = ThreadPoolExecutor(max_workers=4)
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

    def _text_ids(self, text: str) -> list[int]:
        cached = self._ids_cache.get(text)
        if cached is not None:
            return cached
        first = self._first_chunk_text(text)
        prepared, _ = prepare_text_prompt(
            first,
            self.model.pad_with_spaces_for_short_inputs,
            self.model.remove_semicolons,
            self.model.append_terminal_punctuation,
            self.model.capitalize_first_letter,
            self.model.replace_characters,
        )
        ids = self.model.flow_lm.conditioner.tokenizer.encode(prepared)
        if self.max_first_tokens is not None:
            ids = ids[: self.max_first_tokens]
        if len(self._ids_cache) >= 8192:
            self._ids_cache.clear()
        self._ids_cache[text] = ids
        return ids

    def _encode_texts(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
        id_lists = list(self._pool.map(self._text_ids, texts))
        lengths = [len(ids) for ids in id_lists]
        width = max(lengths)
        padded = [[0] * (width - len(ids)) + list(ids) for ids in id_lists]
        tokens = torch.tensor(padded, dtype=torch.long, device=self.device)
        emb = self.model.flow_lm.conditioner(tokens)
        pad = torch.tensor([width - n for n in lengths], dtype=torch.long, device=self.device)
        if int(pad.max().item()) > 0:
            cols = torch.arange(width, device=self.device).unsqueeze(0)
            mask = cols < pad.unsqueeze(1)
            emb = emb.masked_fill(mask.unsqueeze(-1), 0.0)
        return emb, pad, lengths

    def _build_prefixes(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
        text_batch, pad, token_counts = self._encode_texts(texts)
        rows, width, dim = text_batch.shape
        vlen = self.voice.shape[1]
        batch = torch.zeros(rows, vlen + width, dim, device=self.device, dtype=text_batch.dtype)
        batch[:, vlen:] = text_batch
        positions = pad.unsqueeze(1) + torch.arange(vlen, device=self.device).unsqueeze(0)
        batch[torch.arange(rows, device=self.device).unsqueeze(1), positions] = self.voice[0]
        return batch, pad, token_counts

    def _build_text_batch(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
        return self._encode_texts(texts)

    @torch.no_grad()
    def stream(
        self,
        texts: list[str],
        on_chunk: ChunkCallback | None = None,
        max_frames: int | None = None,
        frames_after_eos: int = 2,
        on_stage: StageCallback | None = None,
    ) -> list[torch.Tensor]:
        model = self.model
        flow_lm = model.flow_lm
        batch_size = len(texts)
        device = self.device
        dim = flow_lm.dim

        def mark(row: int, name: str) -> None:
            if on_stage is not None:
                on_stage(row, name, time.perf_counter())

        mark(-1, "stream_start")
        mark(-1, "prep_start")
        use_profile_state = self.voice_state is not None
        if use_profile_state:
            text_batch, text_pad, token_counts = self._build_text_batch(texts)
            mark(-1, "prep_done")
            if max_frames is None:
                max_frames = min(128, max(model._estimate_max_gen_len(c) for c in token_counts) + 8)
            vlen = self._voice_state_len()
            seq_len = vlen + text_batch.shape[1] + max_frames + 4
            state = _clone_state_to_batch(self.voice_state, batch_size, seq_len, device)
            set_state_padding(state, text_pad)
            mark(-1, "state_done")
            empty_tokens = torch.empty(batch_size, 0, dtype=torch.int64, device=device)
            empty_latents = torch.empty(batch_size, 0, flow_lm.ldim, dtype=text_batch.dtype, device=device)
            empty_audio = torch.empty(batch_size, 0, dim, dtype=text_batch.dtype, device=device)
            model._run_flow_lm_and_increment_step(
                model_state=state,
                text_tokens=empty_tokens,
                backbone_input_latents=empty_latents,
                audio_conditioning=text_batch,
            )
            mark(-1, "cond_done")
            prefix = None
        else:
            prefix, pad, token_counts = self._build_prefixes(texts)
            mark(-1, "prep_done")
            if max_frames is None:
                max_frames = min(128, max(model._estimate_max_gen_len(c) for c in token_counts) + 8)
            state = init_states(flow_lm, batch_size, prefix.shape[1] + max_frames + 2)
            set_state_padding(state, pad)
            mark(-1, "state_done")
            mark(-1, "cond_done")
            empty_tokens = torch.empty(batch_size, 0, dtype=torch.int64, device=device)
            empty_audio = torch.empty(batch_size, 0, dim, dtype=prefix.dtype, device=device)

        mimi_steps = int(model.mimi.encoder_frame_rate / model.mimi.frame_rate)
        mimi_state = init_states(model.mimi, batch_size, (max_frames + 4) * mimi_steps)
        mimi_dtype = next(model.mimi.parameters()).dtype
        if mimi_dtype != torch.float32:
            mimi_state = {
                name: {
                    key: (
                        value.to(mimi_dtype)
                        if torch.is_tensor(value) and value.is_floating_point()
                        else value
                    )
                    for key, value in module.items()
                }
                for name, module in mimi_state.items()
            }

        latent = flow_lm.bos_emb.view(1, 1, -1).expand(batch_size, 1, -1)
        audio_chunks: dict[int, list[torch.Tensor]] = {row: [] for row in range(batch_size)}
        row_ids = list(range(batch_size))
        countdown = torch.full((batch_size,), -1, dtype=torch.long, device=device)
        done_cpu = [False] * batch_size
        fade = torch.linspace(0, 1, model.config.mimi.sample_rate // 200, device=device)
        t0 = time.perf_counter()

        pending: list[tuple[torch.Tensor, list[bool], int]] = []

        def emit_frame(frame: torch.Tensor, nd_cpu: list[bool], stp: int, elapsed: float) -> None:
            if stp == 0:
                fade_len = min(fade.numel(), frame.shape[-1])
                frame[:, :fade_len] = frame[:, :fade_len] * fade[:fade_len]
            for local in range(batch_size):
                if done_cpu[local]:
                    continue
                if nd_cpu[local]:
                    done_cpu[local] = True
                    continue
                orig = row_ids[local]
                audio_chunks[orig].append(frame[local])
                if len(audio_chunks[orig]) == 1:
                    mark(orig, "first_emit")
                if on_chunk is not None:
                    on_chunk(orig, frame[local], elapsed)

        def flush_pending(force: bool = False) -> bool:
            if self.overlap is not None:
                return _flush_overlapped(force)
            if not pending:
                return all(done_cpu)
            if not force and len(pending) < self.decode_group:
                return False
            latents = torch.cat([p[0] for p in pending], dim=1)
            decode_input = latents * flow_lm.emb_std + flow_lm.emb_mean
            audio = model.mimi.decode_from_latent(decode_input, mimi_state)
            increment_steps(model.mimi, mimi_state, increment=mimi_steps * len(pending))
            if pending[0][2] == 0:
                mark(-1, "mimi0_done")
            if audio.dim() == 3:
                audio = audio[:, 0]
            frame_samples = audio.shape[-1] // len(pending)
            frames = audio.view(batch_size, len(pending), frame_samples)
            elapsed = time.perf_counter() - t0
            for i, (_, nd_cpu, stp) in enumerate(pending):
                emit_frame(frames[:, i], nd_cpu, stp, elapsed)
            pending.clear()
            return all(done_cpu)

        def _flush_overlapped(force: bool) -> bool:
            if self._inflight is not None:
                self.overlap.wait()
                frames, metas = self._inflight
                self._inflight = None
                elapsed = time.perf_counter() - t0
                for i, (nd_cpu, stp) in enumerate(metas):
                    emit_frame(frames[:, i], nd_cpu, stp, elapsed)
            if not pending:
                return all(done_cpu)
            if not force and len(pending) < self.decode_group:
                return False
            start = pending[0][2]
            latents = torch.cat([p[0] for p in pending], dim=1)
            decode_input = latents * flow_lm.emb_std + flow_lm.emb_mean
            metas = [(p[1], p[2]) for p in pending]
            nframes = len(pending)
            box: dict[str, torch.Tensor] = {}

            def run_decode() -> None:
                box["audio"] = model.mimi.decode_from_latent(decode_input, mimi_state)
                increment_steps(model.mimi, mimi_state, increment=mimi_steps * nframes)

            self.overlap.launch(run_decode)
            pending.clear()
            if force:
                self.overlap.wait()
                audio = box["audio"]
                if start == 0:
                    mark(-1, "mimi0_done")
                if audio.dim() == 3:
                    audio = audio[:, 0]
                frames = audio.view(batch_size, nframes, audio.shape[-1] // nframes)
                self._inflight = (frames, metas)
                elapsed = time.perf_counter() - t0
                for i, (nd_cpu, stp) in enumerate(metas):
                    emit_frame(frames[:, i], nd_cpu, stp, elapsed)
                self._inflight = None
                return all(done_cpu)
            audio = box["audio"]
            if audio.dim() == 3:
                audio = audio[:, 0]
            frames = audio.view(batch_size, nframes, audio.shape[-1] // nframes)
            self._inflight = (frames, metas)
            return False

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
            if step == 0:
                mark(-1, "flow0_done")
            eligible = torch.full_like(
                countdown, step >= model._MIN_FRAMES_BEFORE_EOS, dtype=torch.bool
            )
            fired = is_eos.squeeze(-1).bool() & (countdown < 0) & eligible
            countdown = torch.where(
                fired, torch.full_like(countdown, frames_after_eos), countdown
            )
            countdown = torch.where(countdown > 0, countdown - 1, countdown)
            nd_cpu = (countdown == 0).tolist()

            pending.append((latent, nd_cpu, step))
            force = step == 0 or any(nd_cpu)
            if flush_pending(force=force):
                break

            if self.compact and any(nd_cpu) and not all(done_cpu):
                keep = [i for i, finished in enumerate(done_cpu) if not finished]
                if keep and len(keep) < batch_size:
                    keep_t = torch.tensor(keep, dtype=torch.long, device=device)
                    row_ids = [row_ids[i] for i in keep]
                    done_cpu = [done_cpu[i] for i in keep]
                    state = _slice_model_state(state, keep_t, batch_size)
                    mimi_state = _slice_model_state(mimi_state, keep_t, batch_size)
                    latent = latent.index_select(0, keep_t).contiguous()
                    countdown = countdown.index_select(0, keep_t).contiguous()
                    empty_tokens = (
                        empty_tokens.index_select(0, keep_t).contiguous()
                        if empty_tokens.dim() > 0
                        else torch.empty(len(keep), 0, dtype=torch.int64, device=device)
                    )
                    empty_audio = empty_audio.index_select(0, keep_t).contiguous()
                    batch_size = len(keep)

        flush_pending(force=True)

        out: list[torch.Tensor] = []
        for orig in range(len(audio_chunks)):
            chunks = audio_chunks[orig]
            if chunks:
                merged = torch.cat(chunks)
                out.append(merged if merged.dtype == torch.float32 else merged.float())
            else:
                out.append(torch.zeros(0, device=device))
        return out
