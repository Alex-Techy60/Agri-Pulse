"""Vector memory on Qdrant. Two collections:

  knowledge  -> static domain facts (RAG)        : seeded from data/knowledge/*.md
  memory     -> per-session long-term memory     : written during chat, recalled by session_id

QDRANT_URL empty => in-process Qdrant (no Docker, no cloud, still the real client).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.core.config import get_settings
from app.memory.embeddings import make_embedder

KNOWLEDGE = "knowledge"
MEMORY = "memory"


@dataclass
class Hit:
    text: str
    score: float
    source: str
    payload: dict


class VectorStore:
    def __init__(self):
        s = get_settings()
        self.s = s
        self.embedder = make_embedder()
        self.client = (
            QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None) if s.qdrant_url else QdrantClient(":memory:")
        )
        for name in (KNOWLEDGE, MEMORY):
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    name, vectors_config=models.VectorParams(size=self.embedder.dim, distance=models.Distance.COSINE)
                )

    # ---------------------------------------------------------------- write
    def add(self, collection: str, texts: list[str], payloads: list[dict] | None = None) -> int:
        if not texts:
            return 0
        payloads = payloads or [{} for _ in texts]
        vecs = self.embedder.embed(texts)
        points = [
            models.PointStruct(id=str(uuid.uuid4()), vector=v, payload={**p, "text": t, "ts": time.time()})
            for t, v, p in zip(texts, vecs, payloads)
        ]
        self.client.upsert(collection, points=points)
        return len(points)

    def remember(self, session_id: str, text: str, kind: str = "turn") -> None:
        self.add(MEMORY, [text], [{"session_id": session_id, "kind": kind, "source": "memory"}])

    # ----------------------------------------------------------------- read
    def search(self, collection: str, query: str, k: int | None = None, session_id: str | None = None) -> list[Hit]:
        flt = None
        if session_id:
            flt = models.Filter(must=[models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))])
        res = self.client.query_points(
            collection,
            query=self.embedder.embed([query])[0],
            limit=k or self.s.rag_top_k,
            query_filter=flt,
            with_payload=True,
        )
        hits = [
            Hit(p.payload.get("text", ""), float(p.score), p.payload.get("source", collection), p.payload)
            for p in res.points
            if p.score >= self.s.rag_min_score
        ]
        return hits

    def count(self, collection: str) -> int:
        return self.client.count(collection).count

    # ------------------------------------------------------------- seeding
    def seed_dir(self, path: Path) -> int:
        """Chunk every .md/.txt in `path` by blank-line paragraphs (~500 chars)."""
        n = 0
        for f in sorted(path.glob("**/*")):
            if f.suffix.lower() not in {".md", ".txt"}:
                continue
            chunks = chunk(f.read_text(encoding="utf-8"))
            n += self.add(KNOWLEDGE, chunks, [{"source": f.name} for _ in chunks])
        return n


def chunk(text: str, size: int = 500) -> list[str]:
    out, cur = [], ""
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(cur) + len(para) > size and cur:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}".strip()
    if cur:
        out.append(cur)
    return out


_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
