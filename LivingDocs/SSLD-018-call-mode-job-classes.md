<!-- ss-living-doc v1 -->
# SSLD-018: Call-mode job classes

## STATE
doc_id: SSLD-018
status: DONE
current_task: T004
tasks_done: 4
tasks_total: 4
skeleton: Skeletons/Code/batch/job_classes.py
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-018-call-mode-job-classes.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-018-call-mode-job-classes.md --sync

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

### T001: Create job_classes.py
status: DONE
blocked_reason:
file: Code/batch/job_classes.py
context: This is the first call-mode module. It has no dependency on the server or the model. Create the file exactly.
do:
- [x] 1. CREATE `Code/batch/job_classes.py` with the code block below.

   ```python
   """Job classes and class-aware batch selection for the TTS server."""

   from __future__ import annotations

   import os
   from dataclasses import dataclass
   from enum import Enum
   from queue import Empty
   from typing import Any


   class JobClass(str, Enum):
       CALL_FIRST = "call_first"
       CALL_CONT = "call_cont"
       NORMAL = "normal"


   PRIORITY = {
       JobClass.CALL_FIRST: 0,
       JobClass.CALL_CONT: 1,
       JobClass.NORMAL: 2,
   }


   @dataclass(frozen=True)
   class ClassConfig:
       cls: JobClass
       max_batch: int
       max_frames: int
       window_ms: int


   @dataclass(frozen=True)
   class Config:
       classes: dict[JobClass, ClassConfig]
       normal_busy_max_batch: int
       normal_busy_max_frames: int
       max_rows: int


   def _int(env: Any, key: str, default: int) -> int:
       raw = env.get(key)
       if raw is None or raw == "":
           return default
       return int(raw)


   def load_class_config(env: Any = None) -> Config:
       if env is None:
           env = os.environ
       specs = (
           (JobClass.CALL_FIRST, "CALL_FIRST", 32, 224),
           (JobClass.CALL_CONT, "CALL_CONT", 192, 224),
           (JobClass.NORMAL, "NORMAL", 192, 192),
       )
       default_window = _int(env, "ARSENAL_BATCH_WINDOW_MS", 150)
       classes: dict[JobClass, ClassConfig] = {}
       for cls, prefix, frame_default, batch_default in specs:
           frames = _int(env, f"ARSENAL_{prefix}_MAX_FRAMES", frame_default)
           batch = _int(env, f"ARSENAL_{prefix}_MAX_BATCH", batch_default)
           window = _int(env, f"ARSENAL_{prefix}_WINDOW_MS", default_window)
           classes[cls] = ClassConfig(cls, batch, frames, window)
       return Config(
           classes=classes,
           normal_busy_max_batch=_int(env, "ARSENAL_NORMAL_BUSY_MAX_BATCH", 32),
           normal_busy_max_frames=_int(env, "ARSENAL_NORMAL_BUSY_MAX_FRAMES", 64),
           max_rows=_int(env, "ARSENAL_MAX_ROWS", 224),
       )


   def select_class(queues: dict[JobClass, Any], active_sessions: int = 0) -> JobClass | None:
       for cls in (JobClass.CALL_FIRST, JobClass.CALL_CONT, JobClass.NORMAL):
           q = queues.get(cls)
           if q is not None and not q.empty():
               return cls
       return None


   def normal_limits(cfg: Config, active_sessions: int) -> tuple[int, int]:
       limit = cfg.classes[JobClass.NORMAL].max_batch
       frames = cfg.classes[JobClass.NORMAL].max_frames
       if active_sessions > 0:
           limit = min(limit, cfg.normal_busy_max_batch)
           frames = min(frames, cfg.normal_busy_max_frames)
       return limit, frames


   def select_batch(
       queues: dict[JobClass, Any], cfg: Config, active_sessions: int = 0
   ) -> tuple[JobClass | None, list[Any]]:
       cls = select_class(queues, active_sessions)
       if cls is None:
           return None, []
       limit = cfg.classes[cls].max_batch
       if cls is JobClass.NORMAL:
           limit, _ = normal_limits(cfg, active_sessions)
       q = queues[cls]
       batch: list[Any] = []
       rows = 0
       while len(batch) < limit and rows < cfg.max_rows:
           try:
               job = q.get_nowait()
           except Empty:
               break
           if getattr(job, "cancelled", False):
               continue
           n = len(job.texts)
           if rows + n > cfg.max_rows:
               q.put_nowait(job)
               break
           batch.append(job)
           rows += n
       if not batch:
           return None, []
       return cls, batch
   ```
- [x] 2. CHECK that the file has the line `class JobClass(str, Enum):`.
verify: `python -c "import sys; sys.path.insert(0,'Code'); import batch.job_classes as m; print(m.PRIORITY[m.JobClass.CALL_FIRST])"`
expect: 0
if_fail: Open `Code/batch/job_classes.py`. Make it match the code block in step 1 exactly. Run `verify:` again.
result: 0

### T002: Check class priority
status: DONE
blocked_reason:
file: Code/batch/job_classes.py
context: Proves call_first runs before call_cont, call_cont before normal, and one batch never mixes classes.
do:
- [x] 1. RUN the verify command. Do not edit any file.
verify: `python -c "import sys,queue; sys.path.insert(0,'Code'); from batch.job_classes import *; J=lambda n:type('J',(),{'texts':[n],'cancelled':False})(); q={c:queue.Queue() for c in JobClass}; q[JobClass.NORMAL].put(J('n1')); q[JobClass.CALL_CONT].put(J('c1')); q[JobClass.CALL_FIRST].put(J('f1')); cfg=load_class_config({}); c,b=select_batch(q,cfg,0); assert c is JobClass.CALL_FIRST and b[0].texts==['f1']; c,b=select_batch(q,cfg,0); assert c is JobClass.CALL_CONT; c,b=select_batch(q,cfg,0); assert c is JobClass.NORMAL; print('ok')"`
expect: ok
if_fail: Open `Code/batch/job_classes.py`. Find `def select_class` and `def select_batch`. Make them match the T001 code block. Run `verify:` again.
result: ok

### T003: Check busy caps and row limit
status: DONE
blocked_reason:
file: Code/batch/job_classes.py
context: Proves that active call sessions cap normal work and that one batch never passes max_rows.
do:
- [x] 1. RUN the verify command. Do not edit any file.
verify: `python -c "import sys,queue; sys.path.insert(0,'Code'); from batch.job_classes import *; J=lambda n,k=1:type('J',(),{'texts':[str(n)]*k,'cancelled':False})(); cfg=load_class_config({'ARSENAL_MAX_ROWS':'4'}); q={c:queue.Queue() for c in JobClass}; [q[JobClass.NORMAL].put(J(i)) for i in range(10)]; c,b=select_batch(q,cfg,3); assert c is JobClass.NORMAL and len(b)<=cfg.normal_busy_max_batch and sum(len(j.texts) for j in b)<=4; print('ok')"`
expect: ok
if_fail: Open `Code/batch/job_classes.py`. Find `def normal_limits` and `def select_batch`. Make them match the T001 code block. Run `verify:` again.
result: ok

### T004: Record the implemented revision
status: DONE
blocked_reason:
file: Skeletons/Code/batch/job_classes.py
context: The code now matches spec revision 1. Record that fact in the skeleton. Do not change any other field.
do:
- [x] 1. EDIT `Skeletons/Code/batch/job_classes.py`: find the line `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
verify: `grep -c "@stageset implemented_revision: 1" Skeletons/Code/batch/job_classes.py`
expect: 1
if_fail: Open `Skeletons/Code/batch/job_classes.py`. Find the line that starts with `@stageset implemented_revision:`. Change the number to 1. Run `verify:` again.
result: 1
