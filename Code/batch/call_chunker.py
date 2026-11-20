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
