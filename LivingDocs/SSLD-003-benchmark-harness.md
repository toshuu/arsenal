<!-- ss-living-doc v1 -->
# SSLD-003: Build the benchmark harness workspace

## STATE
doc_id: SSLD-003
status: NOT_STARTED
current_task: T001
tasks_done: 0
tasks_total: 4
skeleton: -
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-003-benchmark-harness.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-003-benchmark-harness.md --sync

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

### T001: Create the benchmark workspace
status: TODO
blocked_reason:
file: Code/pocket-tts-bench/README.md
context: Phase 0 needs one folder for results and voices. This task makes the folder. The model stays in Code/model from SSLD-001.
do:
- [ ] 1. CREATE `Code/pocket-tts-bench/README.md` with the text block below.
- [ ] 2. CREATE `Code/pocket-tts-bench/results/.gitkeep` as an empty file.
- [ ] 3. CREATE `Code/pocket-tts-bench/voices/.gitkeep` as an empty file.

   ```markdown
   # Pocket TTS benchmark

   Phase 0 setup. Read `Ideas/pocket-tts-multilingual-optimization.md`.

   Folders:
   - `results/` holds raw JSON and logs.
   - `voices/` holds reference voice files.
   - The model files are in `Code/model/`.
   ```
verify: `test -f Code/pocket-tts-bench/README.md && test -d Code/pocket-tts-bench/results && test -d Code/pocket-tts-bench/voices && echo ok`
expect: ok
if_fail: Create `Code/pocket-tts-bench/README.md` again. Create the `results/` and `voices/` folders with `.gitkeep`. Run `verify:` again.
result:

### T002: Record the environment versions
status: TODO
blocked_reason:
file: Code/pocket-tts-bench/results/environment.txt
context: The idea requires pinned versions. This task records Python, pip, and GPU details for the benchmark log.
do:
- [ ] 1. RUN `python -V > Code/pocket-tts-bench/results/environment.txt`
- [ ] 2. RUN `pip freeze > Code/pocket-tts-bench/results/pip-freeze.txt`
- [ ] 3. RUN `command -v nvidia-smi >/dev/null && nvidia-smi > Code/pocket-tts-bench/results/gpu.txt || echo "no gpu" > Code/pocket-tts-bench/results/gpu.txt`
verify: `test -s Code/pocket-tts-bench/results/environment.txt && test -s Code/pocket-tts-bench/results/pip-freeze.txt && test -s Code/pocket-tts-bench/results/gpu.txt && echo ok`
expect: ok
if_fail: Run the three commands again. Check that `Code/pocket-tts-bench/results/` exists. Run `verify:` again.
result:

### T003: Create the fixed test-set manifest
status: TODO
blocked_reason:
file: Code/pocket-tts-bench/testset.json
context: Phase 1 needs one fixed list of languages, groups, and voices. This task records it.
do:
- [ ] 1. CREATE `Code/pocket-tts-bench/testset.json` with the JSON block below.
- [ ] 2. CHECK the language count.

   ```json
   {
     "languages": ["en", "hi", "mr", "kn", "ta", "ml", "te"],
     "groups": ["card-64", "long-sentence", "code-mixed"],
     "voices_min": 5,
     "voices_max": 10
   }
   ```
verify: `python -c "import json; d=json.load(open('Code/pocket-tts-bench/testset.json')); print(len(d['languages']))"`
expect: 7
if_fail: Open `Code/pocket-tts-bench/testset.json`. Make it match the JSON block exactly. Run `verify:` again.
result:

### T004: Create the results schema
status: TODO
blocked_reason:
file: Code/pocket-tts-bench/schema.json
context: Every run must save the same fields. This task records the field names.
do:
- [ ] 1. CREATE `Code/pocket-tts-bench/schema.json` with the JSON block below.
- [ ] 2. CHECK the top-level count.

   ```json
   {
     "request": ["t_request", "t_first_audio", "t_first_nonsilent", "t_end", "audio_seconds", "underruns"],
     "run": ["p50_ttfa", "p95_ttfa", "p99_ttfa", "rtf", "memory", "errors"],
     "quality": ["word_error", "prompt_similarity", "utmos"]
   }
   ```
verify: `python -c "import json; d=json.load(open('Code/pocket-tts-bench/schema.json')); print(len(d))"`
expect: 3
if_fail: Open `Code/pocket-tts-bench/schema.json`. Make it match the JSON block exactly. Run `verify:` again.
result:
