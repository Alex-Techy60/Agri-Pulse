"""Embedders. Default is a dependency-free hashing embedder so the project runs
offline on any laptop with zero model downloads. Switch to fastembed (set
EMBEDDINGS=fastembed + `pip install fastembed`) when you want real semantic quality.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

from app.core.config import get_settings

_TOKEN = re.compile(r"[\wऀ-෿]+", re.UNICODE)  # keeps Indic scripts


class HashEmbedder:
    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            toks = _TOKEN.findall(t.lower())
            feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
            for f in feats:
                h = int(hashlib.md5(f.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0 if (h >> 20) & 1 else -1.0
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out


class FastEmbedder:
    def __init__(self):
        from fastembed import TextEmbedding  # lazy import

        self.model = TextEmbedding("BAAI/bge-small-en-v1.5")
        self.dim = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.embed(texts)]


def make_embedder():
    s = get_settings()
    if s.embeddings == "fastembed":
        return FastEmbedder()
    return HashEmbedder(s.embed_dim)
