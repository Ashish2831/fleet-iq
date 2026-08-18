from __future__ import annotations

import hashlib
import math
import re

TOKEN = re.compile(r"[a-z0-9]+")
EMBED_DIMS = 64  # hash-embedding; swap for bge-small (384) / OpenAI (1536) in H


def tokenize(text: str) -> list[str]:
    return TOKEN.findall((text or "").lower())


def embed(text: str, dims: int = EMBED_DIMS) -> list[float]:
    """Deterministic bag-of-tokens embedding. No API key, stable in tests.

    Production: replace with a real encoder; keep the same cosine + RRF path.
    """
    vec = [0.0] * dims
    for tok in tokenize(text):
        digest = hashlib.sha256(tok.encode()).digest()
        for i in range(dims):
            vec[i] += (digest[i % 32] / 127.5) - 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def rrf(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
