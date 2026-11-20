<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/job_classes.py
@stageset source_idea: IDEA-0007
@stageset status: READY
@stageset priority: P0
@stageset spec_revision: 1
@stageset implemented_revision: 1
@stageset planned_in: .stageset/sessions/plan-call-mode.md
@stageset last_updated_in: .stageset/sessions/plan-call-mode.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: job classes and class scheduler

## Purpose

Classify each job. Select the next batch by class priority. Never mix classes in one
batch. Bound normal work while call sessions are active.

## Contract

- `JobClass` is a string enum with values `call_first`, `call_cont`, `normal`.
- Integer priority is `call_first=0`, `call_cont=1`, `normal=2`. Lower value runs first.
- `ClassConfig` holds `cls`, `max_batch`, `max_frames`, `window_ms`.
- `load_class_config()` reads env values. Defaults equal the values in IDEA-0007.
- `select_class(queues, active_sessions)` returns the class to run now:
  1. `call_first` if it has a job.
  2. `call_cont` if it has a job and `call_first` is empty.
  3. `normal` if it has a job.
  Else return `None`.
- `normal_limits(cfg, active_sessions)` returns the busy caps when
  `active_sessions > 0`, else the normal caps.
- `select_batch(queues, cfg, active_sessions)` returns `(JobClass, list[Job])` or
  `(None, [])`. It takes jobs from exactly one class. It stops at that class
  `max_batch` and at `max_rows` total texts.
- If a class queue is below its fill target, the caller may wait up to the class
  `window_ms`. It must not drain another class during that wait.
- The module reads no GPU state and starts no thread.
- A batch list never contains two classes.

## Structure

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any

class JobClass(str, Enum):
    CALL_FIRST = "call_first"
    CALL_CONT = "call_cont"
    NORMAL = "normal"

PRIORITY = {JobClass.CALL_FIRST: 0, JobClass.CALL_CONT: 1, JobClass.NORMAL: 2}

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
```

## Pseudo-code

```text
load_class_config(env=os.environ):
    classes = {}
    for cls, prefix, frame_default, batch_default in [
        (CALL_FIRST, "CALL_FIRST", 32, 224),
        (CALL_CONT,  "CALL_CONT",  192, 224),
        (NORMAL,     "NORMAL",     192, 192),
    ]:
        frames = int(env.get(f"ARSENAL_{prefix}_MAX_FRAMES", frame_default))
        batch  = int(env.get(f"ARSENAL_{prefix}_MAX_BATCH", batch_default))
        window = int(env.get(f"ARSENAL_{prefix}_WINDOW_MS",
                             env.get("ARSENAL_BATCH_WINDOW_MS", 150)))
        classes[cls] = ClassConfig(cls, batch, frames, window)
    return Config(
        classes=classes,
        normal_busy_max_batch=int(env.get("ARSENAL_NORMAL_BUSY_MAX_BATCH", 32)),
        normal_busy_max_frames=int(env.get("ARSENAL_NORMAL_BUSY_MAX_FRAMES", 64)),
        max_rows=int(env.get("ARSENAL_MAX_ROWS", 224)),
    )

select_class(queues, active_sessions):
    for cls in (CALL_FIRST, CALL_CONT, NORMAL):
        if not queues[cls].empty():
            return cls
    return None

select_batch(queues, cfg, active_sessions):
    cls = select_class(queues, active_sessions)
    if cls is None:
        return None, []
    c = cfg.classes[cls]
    batch, rows = [], 0
    limit = c.max_batch
    if cls == NORMAL and active_sessions > 0:
        limit = min(limit, cfg.normal_busy_max_batch)
    while len(batch) < limit and rows < cfg.max_rows:
        try:
            job = queues[cls].get_nowait()
        except Empty:
            break
        if job.cancelled:
            continue
        if rows + len(job.texts) > cfg.max_rows:
            queues[cls].put_nowait(job)
            break
        batch.append(job)
        rows += len(job.texts)
    if not batch:
        return None, []
    return cls, batch
```

## Assumptions

ASSUMPTION: A-40 - The worker has one thread. A `queue.Queue` per class is safe without locks. [UNVERIFIED]
ASSUMPTION: A-41 - `call_first` and `call_cont` need separate queues to keep priority order. [VERIFIED by design]

## Edge cases

- All queues empty: return `(None, [])`.
- A cancelled job at the queue head: drop it and continue.
- A job that would exceed `max_rows`: put it back at the queue head and stop.
- `active_sessions` is unknown: treat it as 0.
- Env value is not an integer: raise `ValueError` at load time.
- A class has no jobs: it does not block a lower class.

## Checks

### CHECK-CALL-CLASS-01 - class order and no mixing

- Command:
  ```bash
  python - <<'PY'
  import queue
  from batch.job_classes import *
  class J:
      def __init__(self, n):
          self.texts = [n]; self.cancelled = False
  qs = {c: queue.Queue() for c in JobClass}
  qs[JobClass.NORMAL].put(J("n1"))
  qs[JobClass.CALL_CONT].put(J("c1"))
  qs[JobClass.CALL_FIRST].put(J("f1"))
  cfg = load_class_config({})
  cls, batch = select_batch(qs, cfg, 0)
  assert cls is JobClass.CALL_FIRST, cls
  assert [j.texts[0] for j in batch] == ["f1"]
  cls, batch = select_batch(qs, cfg, 0)
  assert cls is JobClass.CALL_CONT, cls
  cls, batch = select_batch(qs, cfg, 0)
  assert cls is JobClass.NORMAL, cls
  print("ok")
  PY
  ```
- Predicted output: `ok`
- Pass condition: exit code 0 and output `ok`.
- Fail condition: any assertion error or a batch with two classes.

### CHECK-CALL-CLASS-02 - busy caps and max rows

- Command:
  ```bash
  python - <<'PY'
  import queue, os
  from batch.job_classes import *
  class J:
      def __init__(self, n, k=1):
          self.texts = [str(n)] * k; self.cancelled = False
  cfg = load_class_config({"ARSENAL_MAX_ROWS": "4"})
  qs = {c: queue.Queue() for c in JobClass}
  for i in range(10):
      qs[JobClass.NORMAL].put(J(i))
  cls, batch = select_batch(qs, cfg, 3)
  assert cls is JobClass.NORMAL
  assert len(batch) <= cfg.normal_busy_max_batch
  assert sum(len(j.texts) for j in batch) <= 4
  print("ok")
  PY
  ```
- Predicted output: `ok`
- Pass condition: exit code 0.
- Fail condition: the busy batch cap or the row cap is exceeded.

## References

- `Ideas/IDEA-0007-dual-service-call-mode.md`
- `Code/batch/server.py`
- `Code/batch/scheduler.py`
