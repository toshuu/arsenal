<!-- ss-living-doc v1 -->
# SSLD-001: Set up the environment and download the model

## STATE
doc_id: SSLD-001
status: NOT_STARTED
current_task: T001
tasks_done: 0
tasks_total: 4
skeleton: Skeletons/requirements.txt.skeleton.md
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-001-setup-env.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-001-setup-env.md --sync

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

### T001: Create requirements.txt
status: TODO
blocked_reason:
file: Code/requirements.txt
context: Code/ exists. This task lists the Python packages for Arsenal. It does not pin versions. The probe records the versions.
do:
- [ ] 1. CREATE `Code/requirements.txt` with the text block below. It has 3 lines.

   ```text
   pocket-tts
   huggingface_hub
   numpy
   ```
- [ ] 2. CHECK that `Code/requirements.txt` has exactly 3 words.
verify: `python -c "print(len(open('Code/requirements.txt').read().split()))"`
expect: 3
if_fail: Open `Code/requirements.txt`. Make it match the text block in step 1 exactly. Run `verify:` again.
result:

### T002: Install packages
status: TODO
blocked_reason:
file: Code/requirements.txt
context: Code/requirements.txt exists. This task installs the 3 packages. It needs internet. It can take several minutes.
do:
- [ ] 1. RUN `python -m pip install -r Code/requirements.txt` from the repository root.
- [ ] 2. CHECK that no line of the pip output starts with `ERROR:`.
verify: `python -c "import pocket_tts; print('pocket_tts ok')"`
expect: pocket_tts ok
if_fail: Run `python -m pip install pocket-tts` and then run `verify:` again.
result:

### T003: Download the model files
status: TODO
blocked_reason:
file: Code/model/config.yaml
context: pocket-tts and huggingface_hub are installed. This task downloads the model repo into Code/model. It needs internet. The files are large.
do:
- [ ] 1. RUN `python -c "from huggingface_hub import snapshot_download; snapshot_download('Thanushttk/pocket-tts-multilingual', local_dir='Code/model')"` from the repository root.
- [ ] 2. CHECK that the folder `Code/model` has the files `config.yaml`, `model.safetensors`, and `tokenizer.model`.
verify: `python -c "import os; print(sorted(f for f in ['config.yaml','model.safetensors','tokenizer.model'] if os.path.exists('Code/model/'+f)))"`
expect: ['config.yaml', 'model.safetensors', 'tokenizer.model']
if_fail: Run the command in step 1 again. The download continues where it stopped. Then run `verify:` again.
result:

### T004: Update skeleton metadata
status: TODO
blocked_reason:
file: Skeletons/requirements.txt.skeleton.md
context: All setup tasks are done. This task records that the setup implements spec_revision 1.
do:
- [ ] 1. EDIT `Skeletons/requirements.txt.skeleton.md`: find the text `implemented_revision: 0` and replace it with `implemented_revision: 1`.
- [ ] 2. EDIT `Skeletons/requirements.txt.skeleton.md`: find the text `status: READY` and replace it with `status: DONE`.
verify: `python -c "t=open('Skeletons/requirements.txt.skeleton.md').read(); print(t.count('implemented_revision: 1'), t.count('status: DONE'))"`
expect: 1 1
if_fail: Open `Skeletons/requirements.txt.skeleton.md`. Make the line with `implemented_revision:` end in 1. Make the line with `status:` end in DONE. Run `verify:` again.
result:
