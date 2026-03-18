"""Vector embedding search layer using sentence-transformers.

Replaces TF-IDF (semantic.py) with dense embeddings for higher-quality
semantic retrieval. Uses all-MiniLM-L6-v2 (80MB, fast on Apple Silicon).

Usage:
    from .embeddings import EmbeddingIndex, hybrid_search

    idx = EmbeddingIndex()
    idx.build_index()
    results = idx.search("how does the memory system work", top_k=5)

    # Or use hybrid (FTS5 + embeddings + RRF fusion):
    results = hybrid_search("memory system", top_k=5, session_id="abc")
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("agenticEvolve.embeddings")

CACHE_DIR = Path.home() / ".agenticEvolve" / "cache"
EMBEDDINGS_CACHE = CACHE_DIR / "embeddings.npz"
META_CACHE = CACHE_DIR / "embeddings_meta.json"

# Sentinel for lazy model loading
_model = None


def _load_model():
    """Lazy-load the sentence-transformers model on first use."""
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        log.info("[embeddings] Model loaded: all-MiniLM-L6-v2")
        return _model
    except ImportError:
        log.warning(
            "[embeddings] sentence-transformers not installed — "
            "embedding search disabled"
        )
        return None
    except Exception as e:
        log.error(f"[embeddings] Failed to load model: {e}")
        return None


def _source_mtime() -> float:
    """Return the most recent mtime across DB + markdown sources."""
    from .session_db import DB_PATH

    paths = [
        DB_PATH,
        Path.home() / ".agenticEvolve" / "memory" / "MEMORY.md",
        Path.home() / ".agenticEvolve" / "memory" / "USER.md",
    ]
    mtime = 0.0
    for p in paths:
        try:
            mtime = max(mtime, os.stat(p).st_mtime)
        except OSError:
            pass
    return mtime


def _cache_is_fresh() -> bool:
    """Return True if the npz cache exists and is newer than all source files."""
    if not EMBEDDINGS_CACHE.exists():
        return False
    try:
        cache_mtime = os.stat(EMBEDDINGS_CACHE).st_mtime
        return cache_mtime >= _source_mtime()
    except OSError:
        return False


class EmbeddingIndex:
    """Dense vector index over all memory sources."""

    def __init__(self) -> None:
        self._vectors: Optional[np.ndarray] = None  # (N, dim) float32
        self._docs: list[dict] = []  # [{content, source, meta}, ...]
        self._built_at: Optional[datetime] = None

    # ── Encoding ─────────────────────────────────────────────

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts to normalised embedding vectors.

        Returns:
            np.ndarray of shape (len(texts), dim) or empty (0, 0) on failure.
        """
        model = _load_model()
        if model is None:
            return np.empty((0, 0), dtype=np.float32)
        try:
            vecs = model.encode(texts, show_progress_bar=False,
                                normalize_embeddings=True)
            return np.asarray(vecs, dtype=np.float32)
        except Exception as e:
            log.error(f"[embeddings] Encode failed: {e}")
            return np.empty((0, 0), dtype=np.float32)

    # ── Index building ───────────────────────────────────────

    def build_index(self, force: bool = False) -> int:
        """Build embedding index from all memory sources.

        Extracts text from:
          - Recent session messages (last 30 days)
          - Learnings
          - Instincts
          - MEMORY.md entries (section-delimited)
          - USER.md entries (line-by-line)

        Returns number of documents indexed.
        """
        # Skip rebuild if in-memory index is fresh (< 1 hour old)
        if not force and self._built_at:
            age = (datetime.now(timezone.utc) - self._built_at).total_seconds()
            if age < 3600:
                return len(self._docs)

        # Skip rebuild if on-disk cache is newer than sources
        if not force and self._vectors is None and _cache_is_fresh():
            if self._load_cache():
                return len(self._docs)

        from .session_db import DB_PATH

        docs: list[dict] = []

        # 1. Session messages (last 30 days)
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT m.content, m.role, s.title, s.started_at "
                "FROM messages m JOIN sessions s ON m.session_id = s.id "
                "WHERE m.content IS NOT NULL AND length(m.content) > 20 "
                "AND s.started_at >= datetime('now', '-30 days') "
                "ORDER BY m.timestamp DESC LIMIT 2000"
            ).fetchall()
            for r in rows:
                docs.append({
                    "content": r["content"][:500],
                    "source": "session",
                    "meta": f"{r['title'] or 'untitled'} "
                            f"({(r['started_at'] or '')[:10]})",
                })
            conn.close()
        except Exception as e:
            log.warning(f"Failed to load session messages: {e}")

        # 2. Learnings
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT target, patterns, operational_benefit, full_report, "
                "verdict FROM learnings ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
            for r in rows:
                text = " ".join(filter(None, [
                    r["target"], r["patterns"], r["operational_benefit"],
                    (r["full_report"] or "")[:300],
                ]))
                docs.append({
                    "content": text[:500],
                    "source": "learning",
                    "meta": f"{r['target']} [{r['verdict']}]",
                })
            conn.close()
        except Exception as e:
            log.warning(f"Failed to load learnings: {e}")

        # 3. Instincts
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT pattern, context, confidence FROM instincts "
                "WHERE confidence >= 0.3 ORDER BY confidence DESC LIMIT 200"
            ).fetchall()
            for r in rows:
                text = f"{r['pattern']} {r['context'] or ''}"
                docs.append({
                    "content": text[:500],
                    "source": "instinct",
                    "meta": f"conf:{r['confidence']:.1f}",
                })
            conn.close()
        except Exception as e:
            log.warning(f"Failed to load instincts: {e}")

        # 4. MEMORY.md
        mem_path = Path.home() / ".agenticEvolve" / "memory" / "MEMORY.md"
        if mem_path.exists():
            try:
                for entry in mem_path.read_text().split("\u00a7"):
                    entry = entry.strip()
                    if len(entry) > 15:
                        docs.append({
                            "content": entry[:500],
                            "source": "memory",
                            "meta": "",
                        })
            except Exception:
                pass

        # 5. USER.md
        user_path = Path.home() / ".agenticEvolve" / "memory" / "USER.md"
        if user_path.exists():
            try:
                for line in user_path.read_text().splitlines():
                    line = line.strip()
                    if len(line) > 15:
                        docs.append({
                            "content": line[:500],
                            "source": "user_profile",
                            "meta": "",
                        })
            except Exception:
                pass

        if not docs:
            log.info("[embeddings] No documents for index")
            return 0

        # Encode all documents
        texts = [d["content"] for d in docs]
        vectors = self.encode(texts)
        if vectors.size == 0:
            log.warning("[embeddings] Encoding produced empty vectors")
            return 0

        self._vectors = vectors
        self._docs = docs
        self._built_at = datetime.now(timezone.utc)

        # Persist to disk
        self._save_cache()
        log.info(f"[embeddings] Built index: {len(docs)} docs, "
                 f"dim={vectors.shape[1]}")
        return len(docs)

    # ── Search ───────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Cosine similarity search over the embedding index.

        Returns:
            List of {"content", "source", "meta", "score"} dicts,
            filtered to score >= 0.2.
        """
        if self._vectors is None or len(self._docs) == 0:
            # Try loading from cache
            if not self._load_cache():
                count = self.build_index()
                if count == 0:
                    return []

        if self._vectors is None or self._vectors.size == 0:
            return []

        query_vec = self.encode([query])
        if query_vec.size == 0:
            return []

        # Cosine similarity (vectors are already L2-normalised)
        scores = (self._vectors @ query_vec.T).flatten()

        # Top-k indices
        k = min(top_k, len(scores))
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results: list[dict] = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < 0.2:
                continue
            doc = self._docs[idx]
            results.append({
                "content": doc["content"],
                "source": doc["source"],
                "meta": doc.get("meta", ""),
                "score": score,
            })
        return results

    # ── Incremental update ───────────────────────────────────

    def incremental_update(self, new_texts: list[dict]) -> None:
        """Add new documents without full rebuild.

        Args:
            new_texts: List of dicts with keys: content, source, meta.
        """
        if not new_texts:
            return

        texts = [d["content"] for d in new_texts]
        new_vecs = self.encode(texts)
        if new_vecs.size == 0:
            return

        if self._vectors is not None and self._vectors.size > 0:
            self._vectors = np.vstack([self._vectors, new_vecs])
        else:
            self._vectors = new_vecs

        for d in new_texts:
            self._docs.append({
                "content": d.get("content", ""),
                "source": d.get("source", "unknown"),
                "meta": d.get("meta", ""),
            })

        self._save_cache()
        log.debug(f"[embeddings] Incremental update: +{len(new_texts)} docs, "
                  f"total={len(self._docs)}")

    # ── Cache I/O ────────────────────────────────────────────

    def _save_cache(self) -> None:
        """Persist vectors and metadata to disk."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if self._vectors is not None:
                np.savez_compressed(EMBEDDINGS_CACHE, vectors=self._vectors)
            with open(META_CACHE, "w") as f:
                json.dump({
                    "docs": self._docs,
                    "built_at": (self._built_at.isoformat()
                                 if self._built_at else None),
                    "count": len(self._docs),
                }, f)
        except Exception as e:
            log.error(f"[embeddings] Failed to save cache: {e}")

    def _load_cache(self) -> bool:
        """Load cached vectors and metadata from disk."""
        if self._vectors is not None:
            return True
        if not EMBEDDINGS_CACHE.exists() or not META_CACHE.exists():
            return False
        try:
            data = np.load(EMBEDDINGS_CACHE)
            self._vectors = data["vectors"]

            with open(META_CACHE) as f:
                meta = json.load(f)
            self._docs = meta.get("docs", [])

            built_str = meta.get("built_at")
            if built_str:
                self._built_at = datetime.fromisoformat(built_str)
            else:
                cache_mtime = os.stat(EMBEDDINGS_CACHE).st_mtime
                self._built_at = datetime.fromtimestamp(
                    cache_mtime, tz=timezone.utc
                )

            log.info(f"[embeddings] Loaded cached index: {len(self._docs)} docs")
            return True
        except Exception as e:
            log.debug(f"[embeddings] Failed to load cache: {e}")
            return False


# ── Singleton accessor ───────────────────────────────────────

_default_index: Optional[EmbeddingIndex] = None


def get_index() -> EmbeddingIndex:
    """Return the module-level singleton EmbeddingIndex."""
    global _default_index
    if _default_index is None:
        _default_index = EmbeddingIndex()
    return _default_index


# ── Hybrid search with RRF fusion ────────────────────────────

def hybrid_search(query: str, top_k: int = 5,
                  session_id: str = "") -> list[dict]:
    """Combine FTS5 keyword search with embedding vector search via RRF.

    Reciprocal Rank Fusion: score = sum(1 / (k + rank_i)), k=60.
    This balances keyword-exact matches with semantic similarity.

    Args:
        query: Search query string.
        top_k: Number of results to return.
        session_id: Optional session ID for active-session context.

    Returns:
        Fused ranked list of {"content", "source", "meta", "score"} dicts.
    """
    RRF_K = 60
    fts_results: list[dict] = []
    emb_results: list[dict] = []

    # 1. FTS5 keyword search (lazy import to avoid circular deps)
    try:
        from . import session_db
        raw = session_db.unified_search(query, session_id=session_id,
                                        limit_per_layer=top_k)
        # Strip the semantic layer results that unified_search adds — we
        # replace that with our own embedding search.
        fts_results = [
            r for r in raw
            if not r.get("source", "").startswith("semantic:")
        ]
    except Exception as e:
        log.debug(f"[hybrid] FTS search failed: {e}")

    # 2. Embedding vector search
    try:
        idx = get_index()
        emb_results = idx.search(query, top_k=top_k * 2)
    except Exception as e:
        log.debug(f"[hybrid] Embedding search failed: {e}")

    # If both sides are empty, nothing to fuse
    if not fts_results and not emb_results:
        return []

    # Build content-keyed score map for RRF
    # Key: first 100 chars of content (dedup key)
    scores: dict[str, dict] = {}

    def _key(item: dict) -> str:
        return (item.get("content") or "")[:100]

    for rank, item in enumerate(fts_results, start=1):
        k = _key(item)
        if k not in scores:
            scores[k] = {
                "content": item.get("content", ""),
                "source": item.get("source", "fts"),
                "meta": item.get("meta", ""),
                "score": 0.0,
            }
        scores[k]["score"] += 1.0 / (RRF_K + rank)

    for rank, item in enumerate(emb_results, start=1):
        k = _key(item)
        if k not in scores:
            scores[k] = {
                "content": item.get("content", ""),
                "source": item.get("source", "embedding"),
                "meta": item.get("meta", ""),
                "score": 0.0,
            }
        scores[k]["score"] += 1.0 / (RRF_K + rank)

    # Sort by fused score descending, take top_k
    fused = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return fused[:top_k]
