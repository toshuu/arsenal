<!-- ss-living-doc v1 -->
# SSLD-022: Natural live-call streaming - Phase 0

## STATE
doc_id: SSLD-022
status: DONE
current_task: T006
tasks_done: 6
tasks_total: 6
skeleton: Skeletons/Probes/probe_natural_stream.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-022-natural-live-call-streaming.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-022-natural-live-call-streaming.md --sync

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

## STRATEGY

Target: natural speech + high B + low first-sound time + raw frame streaming.

Premade and keep:

- Raw frame emit: `on_chunk` in `Code/batch/batched_stream.py`.
- Per-row EOS and `compact=True` row removal.
- `decode_group=1` and `overlap_decode`.
- Conditioned voice profile for fast first frame.
- `call_first > call_cont > normal` job classes.
- WS PCM send in `Code/batch/server.py`.

Remove or gate for quality:

- `max_first_tokens=16` in quality mode.
- `pause_compress` in quality mode.
- Fixed `join_chunks` pause in quality mode.

Text policy:

- `utterance`: one job, whole text. Best quality. Normal load.
- `sentence`: split at sentence ends only. High load.
- `latency`: split at first strong clause. Extreme load only.

Late join:

- Short term: bound job length with `sentence` mode.
- Long term: add waiting rows to a running batch. Do this only after Phase 0.

Target gates:

| Gate | Goal B | Status |
| --- | ---: | --- |
| 350 ms | 224 to 448 | Must pass |
| 200 ms | 96 to 224 | Measure |
| 100 ms | 32 to 96 | Measure, report floor |

## TASKS

### T001: Create natural stream probe

status: DONE
blocked_reason:
file: Code/probes/probe_natural_stream.py
context: This probe compares the legacy 16-token policy with sentence and whole-utterance policies. It uses BatchedStream directly.
do:
- [x] 1. CREATE `Code/probes/probe_natural_stream.py` with the code block below.
- [x] 2. CHECK the file has `def main()`.
- [x] 3. RUN `python -m py_compile Code/probes/probe_natural_stream.py`.
verify: `python -m py_compile Code/probes/probe_natural_stream.py`
expect: exit code 0
if_fail: Open `Code/probes/probe_natural_stream.py`. Find the syntax error. Compare the file to the code block in step 1. Run `verify:` again.
result: (no output; exit 0)

### T002: Run smoke for three modes

status: DONE
blocked_reason:
file: Code/probes/probe_natural_stream.py
also_edit: Code/probes/out/natural_stream/
context: Run B=2 for legacy, sentence, and utterance. The T4 must be free. Each run loads the model once.
do:
- [x] 1. RUN `python Code/probes/probe_natural_stream.py --mode legacy --batch 2 --reps 1 --mix same --out Code/probes/out/natural_stream/smoke_legacy.json`.
- [x] 2. RUN `python Code/probes/probe_natural_stream.py --mode sentence --batch 2 --reps 1 --mix same --out Code/probes/out/natural_stream/smoke_sentence.json`.
- [x] 3. RUN `python Code/probes/probe_natural_stream.py --mode utterance --batch 2 --reps 1 --mix same --out Code/probes/out/natural_stream/smoke_utterance.json`.
verify: `python -c "import glob,json; d=[json.load(open(p)) for p in sorted(glob.glob('Code/probes/out/natural_stream/smoke_*.json'))]; print(len(d), [x['mode'] for x in d])"`
expect: 3 ['legacy', 'sentence', 'utterance']
if_fail: Open the first failing command output. Check `nvidia-smi` shows free memory. Run the failed command again. If it still fails, set status BLOCKED.
result: 3 ['legacy','sentence','utterance'] (outputs initially written under Code/model/... then moved to Code/probes/out/natural_stream/)

### T003: Run B=64 same text

status: DONE
blocked_reason:
file: Code/probes/probe_natural_stream.py
also_edit: Code/probes/out/natural_stream/
context: Run B=64 with the same long text for all rows. This measures first frame and batch wall at a medium batch.
do:
- [x] 1. RUN `python Code/probes/probe_natural_stream.py --mode legacy --batch 64 --reps 2 --mix same --out Code/probes/out/natural_stream/b64_legacy.json`.
- [x] 2. RUN `python Code/probes/probe_natural_stream.py --mode sentence --batch 64 --reps 2 --mix same --out Code/probes/out/natural_stream/b64_sentence.json`.
- [x] 3. RUN `python Code/probes/probe_natural_stream.py --mode utterance --batch 64 --reps 2 --mix same --out Code/probes/out/natural_stream/b64_utterance.json`.
verify: `python -c "import glob,json; d=[json.load(open(p)) for p in sorted(glob.glob('Code/probes/out/natural_stream/b64_*.json'))]; print(len(d), sorted({x['batch'] for x in d}))"`
expect: 3 [64]
if_fail: Run the failed command again. Check `nvidia-smi` for memory. If it still fails, set status BLOCKED.
result: 3 [64] (moved from Code/model/... to Code/probes/out/natural_stream/)

### T004: Run B=64 mixed text

status: DONE
blocked_reason:
file: Code/probes/probe_natural_stream.py
also_edit: Code/probes/out/natural_stream/
context: Half the rows use a short text and half use the long text. This shows the per-row tail and compaction behavior.
do:
- [x] 1. RUN `python Code/probes/probe_natural_stream.py --mode sentence --batch 64 --reps 2 --mix mixed --out Code/probes/out/natural_stream/b64_mixed_sentence.json`.
- [x] 2. RUN `python Code/probes/probe_natural_stream.py --mode utterance --batch 64 --reps 2 --mix mixed --out Code/probes/out/natural_stream/b64_mixed_utterance.json`.
verify: `python -c "import glob,json; d=[json.load(open(p)) for p in glob.glob('Code/probes/out/natural_stream/b64_mixed_*.json')]; print(len(d), all(x['last_frame_ms']['max'] > x['last_frame_ms']['min'] for x in d))"`
expect: 2 True
if_fail: Run the failed command again. If the mixed test shows all rows end together, set status BLOCKED and write the JSON path in blocked_reason.
result: 2 True (moved from Code/model/... to Code/probes/out/natural_stream/)

### T005: Check all Phase 0 evidence

status: DONE
blocked_reason:
file: Code/probes/out/natural_stream/
context: Check that all eight JSON files and at least ten WAV files exist. Check that each JSON has no error.
do:
- [x] 1. RUN `python -c "import glob,json; files=sorted(glob.glob('Code/probes/out/natural_stream/*.json')); wavs=sorted(glob.glob('Code/probes/out/natural_stream/*.wav')); print(len(files), len(wavs), all('mode' in json.load(open(p)) for p in files))"`.
- [x] 2. CHECK the output.
verify: `python -c "import glob,json; files=sorted(glob.glob('Code/probes/out/natural_stream/*.json')); wavs=sorted(glob.glob('Code/probes/out/natural_stream/*.wav')); print(len(files), len(wavs), all('mode' in json.load(open(p)) for p in files))"`
expect: 8 10 True
if_fail: Run the missing task again. If a JSON file is missing, run the command that writes it. If a WAV file is missing, set status BLOCKED and write the JSON path in blocked_reason.
result: 8 31 True (>=10 WAVs; all JSONs valid)

### T006: Update probe metadata

status: DONE
blocked_reason:
file: Skeletons/Probes/probe_natural_stream.md
context: All Phase 0 probe runs are done. Record that the probe implements revision 1.
do:
- [x] 1. EDIT `Skeletons/Probes/probe_natural_stream.md`: find line `@stageset implemented_revision: 0` -> `1`.
- [x] 2. EDIT `Skeletons/Probes/probe_natural_stream.md`: find line `@stageset status: READY` -> `DONE`.
verify: `grep -c "@stageset implemented_revision: 1" Skeletons/Probes/probe_natural_stream.md`
expect: 1
if_fail: Open `Skeletons/Probes/probe_natural_stream.md`. Fix metadata lines. Run verify again.
result: implemented_revision=1, status=DONE (grep count 1)
