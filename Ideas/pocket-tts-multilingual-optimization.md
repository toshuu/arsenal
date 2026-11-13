---
id: IDEA-0001
title: Pocket TTS Multilingual: Baseline, Potential, Optimization
status: DISCOVERY
priority: P1
created_at: PENDING
updated_at: PENDING
created_in: .stageset/sessions/ideation-pocket-tts-multilingual.md
updated_in: .stageset/sessions/ideation-pocket-tts-multilingual.md
related_ideas: []
related_skeletons: []
---

# Pocket TTS Multilingual: Baseline, Potential, Optimization

Location: `Ideas/pocket-tts-multilingual-optimization.md`
Repo: `github.com/toshuu/arsenal` (Stageset workspace)
Status: LIVING DOCUMENT. Update it after each work session.

> Follow `.stageset/formats.md` for IDs, revision lines, and timestamps.
> Follow `coder-rules.md` and `ideations-rules.md`.
> Use ASD-STE100-style English. Do not invent numbers, timestamps, or test results.

---

## 1. Goal

Make the Pocket TTS multilingual model very efficient. Choose one track or both:

- **Track G (GPU):** Run on T4 and L4 GPUs. Give the highest number of users
  who all get their first audio quickly in a burst. Then stream the rest chunk by chunk.
  Keep TTFA as low as possible.
- **Track E (Edge):** Make the download small. Run the model on Android.

Work order:

1. **Phase 1: Baseline.** Measure the unmodified model.
2. **Phase 2: Potential report.** Find what can be improved, with evidence.
3. **Phase 3: Optimization.** Do the work. Measure after each change.

Do not start Phase 3 before Phase 2 is done.

## 2. Background

- The owner built **Feather**. Feather is a modified Supertonic (ST3) TTS system.
  It was built for high GPU concurrency and low TTFA.
  It used a custom batcher and fake chunk-by-chunk streaming.
- Feather has two problems:
  - The base model needs 6 flow steps.
  - The owner's distilled 1-step vector estimator fails in the middle of long sentences.
- Pocket TTS multilingual is a candidate replacement. It uses 1 step by design.
  It is autoregressive and decodes audio frame by frame, so streaming can be real.
- The owner thinks this model can be made very efficient. Prove it with data.

## 3. Target model (facts from the model card)

Source: `https://huggingface.co/Thanushttk/pocket-tts-multilingual`

| Item | Value |
|---|---|
| Origin | Community finetune of Kyutai Pocket TTS. Not an official Kyutai release. |
| Base | `kyutai/pocket-tts` (code: `kyutai-labs/pocket-tts`, paper: arXiv 2509.06926) |
| Architecture | Pocket TTS flow LM, 6 layers, distilled from a 24-layer teacher |
| Size | About 0.1B params, F32, about 418 MB. Includes Kyutai codec weights. |
| Text | One SentencePiece tokenizer, 4,000 pieces |
| Languages | English, Hindi, Marathi, Kannada, Tamil, Malayalam, Telugu. Code-mixing works. |
| Audio | 24 kHz |
| Decode | 1 step, temperature 0.3. Guidance is baked in. |
| Voice | Clones a voice from a short wav |
| Intended device | CPU |
| License | CC-BY-4.0. Give credit to Kyutai and the finetune author. |

Card results (64 clips per language, Sarvam dub benchmark):

| Language | Word error | Prompt similarity | UTMOS |
|---|---|---|---|
| English | 6.2% | 0.796 | 4.25 |
| Hindi | 10.5% | 0.904 | 3.62 |
| Marathi | 5.8% | 0.911 | 3.64 |
| Tamil | 11.0% | 0.912 | 3.51 |
| Telugu | 13.8% | 0.897 | 3.70 |
| Kannada | 14.7% | 0.894 | 3.77 |
| Malayalam | 23.7% | 0.863 | 3.63 |

Word error: Whisper large-v3 (English), Indic Transcribe (others).
Prompt similarity: `microsoft/wavlm-base-plus-sv`. UTMOS: 1 to 5 quality estimate.

Basic use (from the card). Run from the folder that holds the repo files:

```python
from pocket_tts import TTSModel
model = TTSModel.load_model(config="config.yaml")
voice = model.get_state_for_audio_prompt("my_voice.wav")
audio = model.generate_audio(voice, "Hello, नमस्ते, how are you?")
```

`weights_path` and `tokenizer_path` in `config.yaml` are relative.
`model.safetensors` and `tokenizer.model` must be in the working directory.

## 4. Definitions

- **TTFA:** Time from request arrival at the server to the first audio sample
  that is not silence. Measure first audio and first non-silent audio separately.
- **Burst concurrency at X ms:** N users send a request at the same moment (t0).
  The largest N where p95 TTFA is below X ms. Test X = 300, 200, 100.
- **Sustained concurrency:** The largest N of streams that keep RTF below 1.0
  for the full audio. No stream may underrun.
- **RTF:** Compute time divided by audio duration.
- **Slot:** The state of one user stream (KV cache, codec state, position).

## 5. Hypotheses (UNVERIFIED estimates)

These come from calculation. Replace them with measured data in Phase 1 and 2.
Assumptions: cached voice state, FP16, slot-based batching, CUDA graphs,
2-frame first chunk, server-side time only.

| Budget | T4 burst N | L4 burst N |
|---|---|---|
| p95 TTFA < 300 ms | 200 to 300 | 350 to 500 |
| p95 TTFA < 200 ms | 100 to 150 | 200 to 300 |
| p95 TTFA < 100 ms | 40 to 60 | 80 to 120 |

- One user alone: about 40 to 70 ms.
- Sustained realtime streams: T4 about 100 to 200, L4 about 200 to 400.
- L4 should be only 1.5x to 2x faster than T4 here.
  Reason: both have about 300 GB/s memory bandwidth and the model is small
  (launch and bandwidth bound, not compute bound).
- T4 has no BF16. Use FP16.

## 6. Open questions (the agent must answer from code and tests)

1. What are the layer width, head count, and context length?
2. What is the frame rate and samples per frame? (Expected: codec at 12.5 Hz. Verify.)
3. How is the voice prompt stored? Is it a KV state? Can it be cached and reused?
4. Does `pocket_tts` already have a streaming API? Which call, and what chunk size?
5. How many frames of leading silence does the model produce?
6. What is the real step time per frame at batch sizes 1, 8, 32, 128?
7. Is the flow head really 1 pass? What does it cost compared to the backbone?
8. Does the codec decoder support streaming state? How big is that state?
9. Does the code allow a batch of different-length texts and different voices?
10. How does quality change on long text? (Feather's old failure: mid-sentence.)

## 7. Phase 0: Setup

- Create the Stageset workspace in `toshuu/arsenal`. Set the code folder in `.stageset/config.yml`.
- Environment: Lightning AI Studio with a T4 and an L4 (separate runs).
- Install `pocket-tts`. Download the model repo files into one folder.
- Pin versions: Python, torch, CUDA, `pocket-tts` commit. Write them in the log.
- Choose a fixed test set:
  - 64 clips per language from the Sarvam dub benchmark, as on the card.
  - Add a long-sentence set (100 to 400 characters) for every language.
  - Add a code-mixed set (Hindi + English, Tamil + English).
  - Add 5 to 10 different reference voices.

## 8. Phase 1: Baseline (no changes to the model)

Run on CPU, T4, and L4. Record all values. Do not tune anything yet.

1. **Reproduce quality.** Compute word error, prompt similarity, UTMOS.
   Compare with the card table. Write the difference.
2. **Single-stream latency.** Measure TTFA (first audio and first non-silent audio),
   RTF, peak memory. Use 20 runs. Report p50, p95.
3. **Batch scaling.** If the code allows batching, measure step time at N = 1, 2, 4, 8, 16, 32, 64.
   If it does not, say so. Measure N parallel processes or threads instead.
4. **Burst test.** N users at t0. N = 1, 4, 8, 16, 32, 64, 128. Record p50, p95, p99 TTFA.
5. **Sustained test.** N streams for 60 seconds each. Record RTF and underruns.
6. **Profile.** Use `torch.profiler`. Record the time split:
   tokenizer, voice prefill, text prefill, backbone step, flow head, codec decode, copy to CPU.
7. **Memory.** Record weights, KV per slot, codec state per slot.

Output of Phase 1: `Ideas/` result file with tables, plus raw JSON in the repo.

## 9. Phase 2: Optimization potential report

Write one report. For each idea, give:

- Expected gain (with the measured profile as evidence).
- Cost and risk.
- Quality risk.
- A test that proves or disproves it.

Ideas to evaluate:

**Track G (GPU)**

- Voice-state cache: prefill once per voice. Copy the state into a slot.
- Slot-based continuous batching. New users join at the next frame boundary.
  No collection window.
- Static shapes and CUDA graphs per batch bucket (1, 2, 4, 8, 16, 32, 64, ...).
- Static KV cache. Avoid ragged tensors in the graph.
- FP16 for backbone and flow head. Check codec stability.
- Fused kernels (SDPA / FlashAttention where T4 supports it, fused norm, fused MLP).
- torch.compile with `mode="max-autotune"` or `reduce-overhead`. Compare against manual CUDA graphs.
- TensorRT or ONNX Runtime for the backbone. Compare. Feather had TRT fall back silently
  to CUDA EP because of a missing `libcublas.so.12`. Check for this and log it.
- Small first chunk: split text at the first clause. Emit after 1 to 2 frames.
- Pinned memory and async copy to CPU. Avoid sync per frame.
- Separate threads or streams: backbone and codec decode in a pipeline.
- Scheduler: priority for new users (prefill first) so burst TTFA stays low.
- Admission control: refuse or queue users when RTF would break.

**Track E (Edge)**

- FP16 weights (about 210 MB expected).
- INT8 weights (about 105 MB expected).
- INT4 on backbone linear layers (about 60 to 70 MB expected).
- Keep flow head and codec decoder in higher precision unless tests pass.
- Export: ONNX Runtime Mobile, ExecuTorch with XNNPACK. Compare.
- Streaming per frame. Cache the voice state on the device.
- Measure on real Android devices (one low-end, one high-end): TTFA, RTF, RAM, battery use.
- Tokenizer on device (SentencePiece).

**Quality guard (both tracks)**

- After each change, run the Phase 1 quality test.
- Set the allowed quality drop after Phase 1. The owner decides the limits.
- Watch Malayalam, Kannada, Telugu first. They have the weakest baseline.
- Watch long sentences and code-mixed text.

## 10. Phase 3: Optimization work

- Work in small steps. One change per step.
- After each step: run speed tests and quality tests. Record the numbers.
- Keep a change only if it helps and quality stays inside the limit.
- If a step fails, keep the failure in the log. Do not delete it.
- Build the serving layer after the engine is fast:
  WebSocket or HTTP streaming API, request queue, slot manager, metrics endpoint.

## 11. Harness requirements

Write one harness. Same harness for all phases.

- Inputs: language set, voice set, N, hardware label, model variant label.
- Burst mode: all N requests start from a barrier. Use a monotonic clock.
- Output per request: t_request, t_first_audio, t_first_nonsilent, t_end, audio_seconds, underruns.
- Output per run: p50, p95, p99 TTFA, RTF, memory, error count.
- Save raw JSON and a short Markdown summary.
- Save the quality scores per language per variant.
- Silence threshold must be a fixed, logged value.

## 12. Rules for the coding agent

- Read `coder-rules.md` first.
- Write what you run and what you observe. Use simple English.
- Mark errors you cannot solve. The next planning session reads them.
- Do not claim a speedup without a measurement in the log.
- Do not report a local commit as a push.
- Update skeleton implementation metadata only after checks pass.

## 13. Risks

- Quantization may hurt low-resource languages first.
- Leading silence may make first word later than first audio.
- Long-text drift in an autoregressive model (different from Feather's failure).
- The model is a community finetune. Support and updates are not certain.
- Hindi, Tamil, Telugu, Kannada, and Malayalam word errors are higher than English.
  They may not be good enough for the product. Decide after the baseline.
- Wrong shared-slot handling can leak one user's audio state into another user's stream.
  Test for isolation.

## 14. Decisions

(Empty. Add one line per decision with date, from the format file.)

## 15. Living log

(Empty. Add one entry per work session. Include: what was run, what was observed, what failed, next step.)
