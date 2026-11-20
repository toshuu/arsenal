<!-- ss-living-doc v1 -->
# SSLD-019: Call-mode chunker

## STATE
doc_id: SSLD-019
status: DONE
current_task: T004
tasks_done: 4
tasks_total: 4
skeleton: Skeletons/Code/batch/call_chunker.py
spec_revision: 1
next_command: python scripts/ss-living-doc.py LivingDocs/SSLD-019-call-mode-chunker.md --next
sync_command: python scripts/ss-living-doc.py LivingDocs/SSLD-019-call-mode-chunker.md --sync

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

### T001: Create call_chunker.py
status: DONE
blocked_reason:
file: Code/batch/call_chunker.py
context: This module makes the short first chunk for voice calls. It has no dependency on the server. Create the file exactly.
do:
- [x] 1. CREATE `Code/batch/call_chunker.py` with the code block below.

   ```python
   """Call-mode text chunker: short first chunk, then normal chunks."""

   from __future__ import annotations

   import re
   import threading
   from typing import Any, Callable

   CALL_MODE = "call"
   _NO_PUNCT_WORDS = 6
   _CLAUSE = re.compile(r"(.+?[.?!;:,])(\s+|$)", re.S)


   def first_clause(text: str, min_words: int = 4, max_words: int = 8) -> tuple[str, str]:
       cleaned = " ".join(text.split())
       if not cleaned:
           return "", ""
       match = _CLAUSE.match(cleaned)
       if match is not None:
           head = match.group(1).strip()
           words = head.split()
           if len(words) > max_words:
               head = " ".join(words[:max_words])
       else:
           words = cleaned.split()
           n = max_words if len(words) <= max_words else _NO_PUNCT_WORDS
           n = max(n, min(min_words, len(words)))
           head = " ".join(words[:n])
       rest = cleaned[len(head) :].strip()
       return head, rest


   def split_call_text(stream: Any, text: str, first_max_frames: int) -> list[str]:
       first, rest = first_clause(text)
       if not first:
           return [""]
       guard = 0
       while not stream._fits_frame_budget(first):
           words = first.split()
           if len(words) <= 1:
               raise ValueError("one word exceeds the call first-chunk budget")
           rest = (words[-1] + (" " + rest if rest else "")).strip()
           first = " ".join(words[:-1])
           guard += 1
           if guard > 64:
               raise ValueError("cannot fit the call first chunk")
       chunks = [first]
       if rest:
           chunks.extend(stream._text_chunks(rest))
       return chunks


   class ChunkCache:
       def __init__(self, maxsize: int = 4096) -> None:
           self.maxsize = maxsize
           self._lock = threading.Lock()
           self._data: dict[Any, list[str]] = {}

       def __len__(self) -> int:
           with self._lock:
               return len(self._data)

       def get_or_split(self, key: Any, fn: Callable[[], list[str]]) -> list[str]:
           with self._lock:
               if key in self._data:
                   return list(self._data[key])
           value = fn()
           with self._lock:
               if len(self._data) >= self.maxsize:
                   self._data.clear()
               self._data[key] = list(value)
           return list(value)


   def warm_ids(stream: Any, texts: list[str]) -> list[list[int]]:
       pool = getattr(stream, "_pool", None)
       if pool is None:
           return [stream._text_ids(text) for text in texts]
       return list(pool.map(stream._text_ids, texts))
   ```
- [x] 2. CHECK that the file has the line `class ChunkCache:`.
verify: `python -c "import sys; sys.path.insert(0,'Code'); import batch.call_chunker as m; print(m.CALL_MODE)"`
expect: call
if_fail: Open `Code/batch/call_chunker.py`. Make it match the code block in step 1 exactly. Run `verify:` again.
result: call

### T002: Check the first clause rule
status: DONE
blocked_reason:
file: Code/batch/call_chunker.py
context: Proves a punctuation clause is the first chunk and that text without punctuation uses 6 words.
do:
- [x] 1. RUN the verify command. Do not edit any file.
verify: `python -c "import sys; sys.path.insert(0,'Code'); from batch.call_chunker import first_clause; f,r=first_clause('Hello there, this is a long sentence for the call.'); assert f=='Hello there,' and r.startswith('this is a long'); f,r=first_clause('Please read this sentence.'); assert f=='Please read this sentence.'; f,r=first_clause('one two three four five six seven eight nine ten'); assert f=='one two three four five six'; print('ok')"`
expect: ok
if_fail: Open `Code/batch/call_chunker.py`. Find `def first_clause`. Make it match the T001 code block. Run `verify:` again.
result: ok

### T003: Check the chunk cache
status: DONE
blocked_reason:
file: Code/batch/call_chunker.py
context: Proves one split per key and a bounded cache size.
do:
- [x] 1. RUN the verify command. Do not edit any file.
verify: `python -c "import sys; sys.path.insert(0,'Code'); from batch.call_chunker import ChunkCache; c=ChunkCache(maxsize=2); n=[0]; fn=lambda:(n.__setitem__(0,n[0]+1) or ['a','b']); assert c.get_or_split(('x',32),fn)==['a','b']; assert c.get_or_split(('x',32),fn)==['a','b']; assert n[0]==1; [c.get_or_split((k,32),fn) for k in ('y','z')]; assert len(c)<=2; print('ok')"`
expect: ok
if_fail: Open `Code/batch/call_chunker.py`. Find `class ChunkCache`. Make it match the T001 code block. Run `verify:` again.
result: ok

### T004: Record the implemented revision
status: DONE
blocked_reason:
file: Skeletons/Code/batch/call_chunker.py
context: The code now matches spec revision 1. Record that fact in the skeleton. Do not change any other field.
do:
- [x] 1. EDIT `Skeletons/Code/batch/call_chunker.py`: find the line `@stageset implemented_revision: 0` and replace it with `@stageset implemented_revision: 1`.
verify: `grep -c "@stageset implemented_revision: 1" Skeletons/Code/batch/call_chunker.py`
expect: 1
if_fail: Open `Skeletons/Code/batch/call_chunker.py`. Find the line that starts with `@stageset implemented_revision:`. Change the number to 1. Run `verify:` again.
result: 1
