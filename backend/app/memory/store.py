"""Vector memory on Qdrant. Two collections:

  knowledge  -> static domain facts (RAG)        : seeded from data/knowledge/*.md
  memory     -> per-session long-term memory     : written during chat, recalled by session_id

QDRANT_URL empty => in-process Qdrant (no Docker, no cloud, still the real client).
"""
from __future__ import annotations

import re

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

    def forget_session(self, session_id: str) -> None:
        """Delete everything remembered for one session (a chat the person deleted must not linger in recalled memory)."""
        flt = models.Filter(must=[models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))])
        self.client.delete(MEMORY, points_selector=models.FilterSelector(filter=flt))

    # ----------------------------------------------------------------- read
    def search(self, collection: str, query: str, k: int | None = None, session_id: str | None = None) -> list[Hit]:
        want = k or self.s.rag_top_k
        if collection == KNOWLEDGE:
            # The embedding is a hash of character n-grams: good at "same words", weak at "the right paragraph". Fetch a wider set and
            # rerank by how many of the question's words (crop, scheme, season, number) the chunk really contains.
            wide = self._vector_search(collection, query, max(want * 4, KNOWLEDGE_RERANK_POOL), session_id, floor=-1.0)  # no vector floor: a table of numbers scores ~0
            share = _idf_share(query, wide)
            ranked = sorted(wide, key=lambda h: -(h.score + 0.9 * share(h)))
            # relevant if the embedding likes it OR the chunk contains a fair (rarity-weighted) share of the question's words
            return [h for h in ranked if h.score >= self.s.rag_min_score or share(h) >= LEXICAL_MIN_SHARE][:want]
        return self._vector_search(collection, query, want, session_id)

    def _vector_search(self, collection: str, query: str, limit: int, session_id: str | None, floor: float | None = None) -> list[Hit]:
        flt = None
        if session_id:
            flt = models.Filter(must=[models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))])
        res = self.client.query_points(
            collection,
            query=self.embedder.embed([query])[0],
            limit=limit,
            query_filter=flt,
            with_payload=True,
        )
        hits = [
            Hit(p.payload.get("text", ""), float(p.score), p.payload.get("source", collection), p.payload)
            for p in res.points
            if p.score >= (self.s.rag_min_score if floor is None else floor)
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
            meta, body = split_front_matter(f.read_text(encoding="utf-8"))
            chunks = chunk(body)
            # every chunk carries its document's title and date, so the answer can name the document it used
            date = " ".join(meta.get("posted", "").split()[:3])
            head = f"[{meta['title']} - {date}] " if meta.get("title") else ""
            keep = {k: v for k, v in meta.items() if k in ("title", "url", "posted", "release_id", "fetched")}
            n += self.add(KNOWLEDGE, [head + c for c in chunks], [{"source": f.name, **keep} for _ in chunks])
        return n


LEXICAL_MIN_SHARE = 0.3  # a chunk with this share of the question's words is relevant even if its embedding is not
KNOWLEDGE_RERANK_POOL = 400  # the whole document set is a few hundred chunks at most: rerank all of it, not just the nearest few
_STOP = {"the", "and", "for", "what", "how", "much", "does", "are", "was", "who", "when", "where", "which", "with", "this", "that", "from", "have", "can", "you", "your", "about", "pay", "get"}


def _terms(text: str) -> set[str]:
    """Words worth matching: Latin words of 3+ letters (not filler), numbers, Devanagari words of 2+ letters."""
    words = (m.lower() for m in re.findall(r"[A-Za-z]{3,}|\d[\d,.]*|[\u0900-\u097f]{2,}", text or ""))
    return {(w[:-1] if len(w) > 4 and w.endswith("s") and w.isascii() else w) for w in words if w not in _STOP}  # crop/crops, instalment/instalments


def _idf_share(query: str, pool: list) -> "callable":
    """h -> the share of the question's words found in chunk h, each word weighted by how rare it is across the pool (idf), so
    "wheat" counts for more than "minimum support price" when every price chunk has those. Words that occur in no chunk (a Hindi
    word against English documents) are left out of the denominator instead of dragging every chunk down."""
    import math

    docs = [_terms(h.text) for h in pool]
    n = max(len(docs), 1)
    weights = {}
    for t in _terms(query):
        df = sum(1 for d in docs if t in d)
        if df:
            weights[t] = math.log(1 + n / df)
    total = sum(weights.values()) or 1.0
    by_id = {id(h): d for h, d in zip(pool, docs)}
    return lambda h: sum(w for t, w in weights.items() if t in by_id.get(id(h), set())) / total


def split_front_matter(text: str) -> tuple[dict, str]:
    """'key: value' lines above a line of three dashes -> ({key: value}, the rest). No header -> ({}, text)."""
    head, sep, rest = text.partition("\n---\n")
    if not sep or not all(":" in ln for ln in head.splitlines() if ln.strip()):
        return {}, text
    return {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in head.splitlines() if ln.strip())}, rest


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
