"""Call-mode chunker: sentence-level boundaries, naturalness first."""

from __future__ import annotations

import re
import threading
from typing import Any, Callable

CALL_MODE = "call"
_SENT_RE = re.compile(r"(.+?[.!?])(\s+|$)", re.S)
_CLAUSE_RE = re.compile(r"(.+?[,;:])(\s+|$)", re.S)
_FRAMES_PER_WORD = 7


def _clean(text: str) -> str:
    return " ".join(text.split())


def _words(text: str) -> list[str]:
    t = _clean(text)
    return t.split() if t else []


def split_by_frame_budget(text: str, audio_frames: int) -> list[str]:
    cleaned = _clean(text)
    if not cleaned:
        return [""]
    per = max(1, audio_frames // _FRAMES_PER_WORD)
    words = cleaned.split()
    return [" ".join(words[i:i + per]) for i in range(0, len(words), per)]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", " ".join(re.findall(r"[a-z0-9']+", s.lower()))).strip()


def _split_sentences(text: str) -> list[str]:
    t = _clean(text)
    if not t:
        return []
    out = []
    pos = 0
    for m in _SENT_RE.finditer(t + " "):
        s = m.group(1).strip()
        if s:
            out.append(s)
        pos = m.end()
    tail = _clean(t[len("".join(m.group(0) for m in _SENT_RE.finditer(t + " "))):])
    if tail:
        out.append(tail)
    return out or [t]


def _split_long_sentence(s: str, cap_words: int = 25) -> list[str]:
    ws = _words(s)
    if len(ws) <= cap_words:
        return [s]
    # strongest clause boundary: prefer ; : , then conjunction
    parts = [m.group(1).strip() for m in _CLAUSE_RE.finditer(s + " ")]
    consumed = "".join(m.group(0) for m in _CLAUSE_RE.finditer(s + " "))
    tail = _clean(s[len(_clean(consumed)):])
    if tail:
        parts.append(tail)
    if len(parts) <= 1:
        # fallback: split at conjunction near middle
        best = None
        for m in re.finditer(r"\b(and|but|so|because|which|that)\b", s, re.I):
            left = len(_words(s[:m.start()]))
            right = len(ws) - left
            if left >= 6 and right >= 6:
                score = abs(left - right)
                if best is None or score < best[0]:
                    best = (score, m.start(), m.end())
        if best:
            _, a, b = best
            left = s[:a].strip(" ,;:")
            right = s[b:].strip()
            if left and right:
                return _split_long_sentence(left, cap_words) + _split_long_sentence(right, cap_words)
        # hard fallback: should be rare; split at word boundary near cap
        left = " ".join(ws[:cap_words]).strip()
        right = " ".join(ws[cap_words:]).strip()
        return [left] + (_split_long_sentence(right, cap_words) if right else [])
    # merge clause parts into <=cap chunks, preferring boundaries
    chunks = []
    cur = ""
    for p in parts:
        p = _clean(p)
        if not p:
            continue
        cand = (cur + " " + p).strip() if cur else p
        if not cur:
            cur = p
            continue
        if len(_words(cand)) <= cap_words:
            cur = cand
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    # if any still too long, recurse
    final = []
    for c in chunks:
        if len(_words(c)) > cap_words:
            final.extend(_split_long_sentence(c, cap_words))
        else:
            final.append(c)
    return final or [s]


def estimate_frame_cap(text: str, margin: int = 16, multiplier: int = 3, lo: int = 24, hi: int = 192) -> int:
    n = 0
    try:
        # caller may pass stream-like with tokenizer; prefer token count if available
        pass
    except Exception:
        pass
    n = len(_words(text))
    return max(lo, min(hi, n * multiplier + margin))


def estimate_first_max_frames(stream: Any, first_text: str, margin: int = 16, lo: int = 24, hi: int = 192) -> int:
    try:
        ids = stream._text_ids(first_text)
        n = len(ids) if hasattr(ids, "__len__") else len(_words(first_text))
    except Exception:
        n = len(_words(first_text))
    return max(lo, min(hi, int(n * 3 + margin)))


def split_call_text(stream: Any, text: str, first_max_frames: int) -> list[str]:
    cleaned = _clean(text)
    if not cleaned:
        return [""]
    # Naturalness first: keep short/medium utterances whole to avoid model-prosody breaks.
    if len(_words(cleaned)) <= 35:
        return [cleaned]
    sentences = _split_sentences(cleaned)
    if not sentences:
        sentences = [cleaned]
    # first chunk = first complete sentence (cap ~25 words)
    first_parts = _split_long_sentence(sentences[0], cap_words=25)
    chunks: list[str] = [first_parts[0]]
    # remaining of first sentence become their own chunks/sentences
    for p in first_parts[1:]:
        chunks.append(p)
    for s in sentences[1:]:
        for p in _split_long_sentence(s, cap_words=25):
            chunks.append(p)

    # ensure no empty and integrity
    chunks = [_clean(c) for c in chunks if _clean(c)]
    if not chunks:
        chunks = [cleaned]
    if _norm(" ".join(chunks)) != _norm(cleaned):
        chunks = [cleaned]
    # ensure frame cap fit - should not truncate; enlarge budget expectation by splitting long sentence already done
    # but keep as-is; caller sets cap tokens*3+16
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
