<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/call_chunker.py
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

# Implementation: call-mode text chunker

## Purpose

Split text for voice calls into a short first chunk and longer later chunks. Keep
one voice conditioning for all chunks. Cache the result. Keep the event loop free.

## Contract

- `first_clause(text, min_words=4, max_words=8) -> tuple[str, str]` returns
  `(first, rest)`. `first` is the first clause with 4 to 8 words. Split points are
  `.`, `?`, `!`, `;`, `:`, `,`, and the first clause end. If no split point
  exists, use the first 6 words.
- `split_call_text(stream, text, first_max_frames) -> list[str]` returns the first
  chunk plus the remaining chunks. The first chunk must fit `first_max_frames`.
  If it does not fit, move words from the tail of the first chunk to the rest
  until it fits. Raise `ValueError` if one word cannot fit.
- Later chunks use `stream._text_chunks(rest)`. This keeps the existing long-text
  splitter, frame guard, and voice behavior.
- `ChunkCache(maxsize=4096)` is a thread-safe bounded map. Key is
  `(text, first_max_frames)`. `get_or_split(key, fn)` returns the list. A full
  cache clears itself, same as `BatchedStream._chunk_cache`.
- `warm_ids(stream, texts)` calls `stream._text_ids` through `stream._pool` for
  each text. This fills the id cache off the caller thread. It does not run the
  GPU.
- `CALL_MODE = "call"`. Cache keys must not collide with normal-mode keys.
- No GPU work on the event loop. Callers run `split_call_text` and `warm_ids` in
  a worker thread or the existing chunk pool.

## Structure

```python
import re, threading
from collections import OrderedDict

_CLAUSE = re.compile(r"(.+?[.?!;:,])(\s+|$)", re.S)

def first_clause(text, min_words=4, max_words=8): ...
def split_call_text(stream, text, first_max_frames): ...
class ChunkCache: ...
def warm_ids(stream, texts): ...
```

## Pseudo-code

```text
first_clause(text, min_words, max_words):
    cleaned = " ".join(text.split())
    if cleaned is empty:
        return "", ""
    match = _CLAUSE.match(cleaned)
    if match is not None:
        head = match.group(1).strip()
        words = head.split()
        if len(words) > max_words:
            head = " ".join(words[:max_words])
    else:
        words = cleaned.split()
        n = max_words if len(words) <= max_words else 6
        n = max(n, min(min_words, len(words)))
        head = " ".join(words[:n])
    rest = cleaned[len(head):].strip()
    return head, rest

split_call_text(stream, text, first_max_frames):
    first, rest = first_clause(text)
    if first is empty:
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
```

If a clause match exists, keep it even when it has fewer than `min_words` words.
`min_words` applies only to text with no punctuation. If the text has no
punctuation and more than `max_words` words, use the first 6 words.

`ChunkCache.get_or_split`:

```text
with lock:
    if key in map: move key to end; return list(value)
value = fn()
with lock:
    if len(map) >= maxsize: map.clear()
    map[key] = list(value)
return list(value)
```

## Assumptions

ASSUMPTION: A-42 - `BatchedStream._fits_frame_budget` and `_text_chunks` are
stable and safe to call from one worker thread at a time. [UNVERIFIED]
ASSUMPTION: A-43 - A first chunk of 4 to 8 words fits a 24 to 48 frame budget for
the reference voice. [UNVERIFIED]
ASSUMPTION: A-44 - Clause splitting at punctuation gives an audible clean break.
[UNVERIFIED] The listening gate must check this.

## Edge cases

- Empty text: return `[""]` only if the caller already validated the text. The
  server rejects empty text with 422 before chunking.
- One long word: raise `ValueError`. The server returns 413.
- No punctuation: first 6 words.
- Text shorter than `min_words`: first chunk is the full text and `rest` is empty.
- Unsupported punctuation: treat it as a normal character.
- Concurrent calls: the lock protects the cache. The stream is used by one worker.
- Cache miss storm: the cache clears at the limit. It does not raise.

## Checks

### CHECK-CALL-CHUNK-01 - first clause rules

- Command:
  ```bash
  python - <<'PY'
  from batch.call_chunker import first_clause
  f, r = first_clause("Hello there, this is a long sentence for the call.")
  assert f == "Hello there,", f
  assert r.startswith("this is a long"), r
  f, r = first_clause("Please read this sentence.")
  assert f == "Please read this sentence.", (f, r)
  f, r = first_clause("one two three four five six seven eight nine ten")
  assert f == "one two three four five six", f
  print("ok")
  PY
  ```
- Predicted output: `ok`
- Pass condition: exit code 0.
- Fail condition: any assertion error.

### CHECK-CALL-CHUNK-02 - cache and split

- Command:
  ```bash
  python - <<'PY'
  from batch.call_chunker import ChunkCache
  c = ChunkCache(maxsize=2)
  calls = {"n": 0}
  def fn():
      calls["n"] += 1
      return ["a", "b"]
  assert c.get_or_split(("x", 32), fn) == ["a", "b"]
  assert c.get_or_split(("x", 32), fn) == ["a", "b"]
  assert calls["n"] == 1, calls
  c.get_or_split(("y", 32), fn)
  c.get_or_split(("z", 32), fn)
  assert len(c) <= 2
  print("ok")
  PY
  ```
- Predicted output: `ok`
- Pass condition: exit code 0. The function runs once for a repeated key.
- Fail condition: a duplicate call for the same key or a cache over the limit.

### CHECK-CALL-CHUNK-03 - chunking cost at B=224

- Command: the `probe_call_mode.md` ramp at B=224, `max_frames=32`.
- Predicted output: `handler_to_chunks_done` p95 < 30 ms.
- Pass condition: the run report shows p95 < 30 ms.
- Fail condition: p95 at or above 30 ms after cache warm and batched tokenization.

## References

- `Ideas/IDEA-0007-dual-service-call-mode.md`
- `Code/batch/batched_stream.py` (`_text_chunks`, `_fits_frame_budget`)
- `Code/batch/server.py` (`chunks_for`)
