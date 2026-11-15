"""Portable batching helpers: bucketing and admission control."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AdmittedBatch:
    texts: list[str]
    bucket: int
    dropped: int


def estimate_tokens(text: str) -> int:
    # Cheap portable estimate; replace with tokenizer length when available.
    return max(1, len(text.split()))


def bucket_texts(texts: list[str], bucket_size: int = 8) -> dict[int, list[str]]:
    buckets: dict[int, list[str]] = {}
    for text in texts:
        n = estimate_tokens(text)
        key = ((n + bucket_size - 1) // bucket_size) * bucket_size
        buckets.setdefault(key, []).append(text)
    return dict(sorted(buckets.items()))


def admit_batches(texts: list[str], max_batch: int, bucket_size: int = 8) -> list[AdmittedBatch]:
    out: list[AdmittedBatch] = []
    for key, group in bucket_texts(texts, bucket_size=bucket_size).items():
        for i in range(0, len(group), max_batch):
            chunk = group[i : i + max_batch]
            dropped = 0
            out.append(AdmittedBatch(texts=chunk, bucket=key, dropped=dropped))
    return out
