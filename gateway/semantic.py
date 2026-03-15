"""Semantic search layer using TF-IDF + cosine similarity.

Augments FTS5 keyword search with semantic scoring. Works locally,
no API calls needed. Can be upgraded to proper embeddings later.

Usage:
    from .semantic import semantic_search, build_corpus

    # Build/update corpus from DB (call periodically or on session end)
    build_corpus()

    # Search — returns scored results
    results = semantic_search("how does the memory system work", top_k=5)
"""
import logging
import sqlite3
import pickle
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger("agenticEvolve.semantic")

CACHE_DIR = Path.home() / ".agenticEvolve" / "cache"
CORPUS_CACHE = CACHE_DIR / "tfidf_corpus.pkl"

# Lazy-loaded globals
_vectorizer = None
_tfidf_matrix = None
_corpus_docs = None  # list of {"id": ..., "content": ..., "source": ..., "meta": ...}
_corpus_built_at = None


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def build_corpus(force: bool = False) -> int:
    """Build TF-IDF corpus from all memory layers.

    Extracts text from:
      - Recent session messages (last 30 days, assistant + user)
      - All learnings
      - All instincts
      - MEMORY.md entries
      - USER.md entries

    Returns number of documents in corpus.
    """
    global _vectorizer, _tfidf_matrix, _corpus_docs, _corpus_built_at

    # Skip rebuild if cache is fresh (< 1 hour old) unless forced
    if not force and _corpus_built_at:
        age = (datetime.now(timezone.utc) - _corpus_built_at).total_seconds()
        if age < 3600:
            return len(_corpus_docs) if _corpus_docs else 0

    from .session_db import DB_PATH

    docs = []

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
                "meta": f"{r['title'] or 'untitled'} ({(r['started_at'] or '')[:10]})",
            })
        conn.close()
    except Exception as e:
        log.warning(f"Failed to load session messages: {e}")

    # 2. Learnings
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT target, patterns, operational_benefit, full_report, verdict "
            "FROM learnings ORDER BY created_at DESC LIMIT 200"
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
            for entry in mem_path.read_text().split("§"):
                entry = entry.strip()
                if len(entry) > 15:
                    docs.append({"content": entry[:500], "source": "memory", "meta": ""})
        except Exception:
            pass

    # 5. USER.md
    user_path = Path.home() / ".agenticEvolve" / "memory" / "USER.md"
    if user_path.exists():
        try:
            for line in user_path.read_text().splitlines():
                line = line.strip()
                if len(line) > 15:
                    docs.append({"content": line[:500], "source": "user_profile", "meta": ""})
        except Exception:
            pass

    if not docs:
        log.info("[semantic] No documents for corpus")
        return 0

    # Build TF-IDF matrix
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = [d["content"] for d in docs]
        vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)

        _vectorizer = vectorizer
        _tfidf_matrix = matrix
        _corpus_docs = docs
        _corpus_built_at = datetime.now(timezone.utc)

        # Persist to disk
        _ensure_cache_dir()
        with open(CORPUS_CACHE, "wb") as f:
            pickle.dump({"vectorizer": vectorizer, "matrix": matrix, "docs": docs}, f)

        log.info(f"[semantic] Built corpus: {len(docs)} docs, {matrix.shape[1]} features")
        return len(docs)

    except ImportError:
        log.warning("[semantic] sklearn not available, skipping corpus build")
        return 0
    except Exception as e:
        log.error(f"[semantic] Failed to build corpus: {e}")
        return 0


def _load_cache() -> bool:
    """Load cached corpus from disk. Returns True if loaded."""
    global _vectorizer, _tfidf_matrix, _corpus_docs, _corpus_built_at

    if _vectorizer is not None:
        return True

    if not CORPUS_CACHE.exists():
        return False

    try:
        with open(CORPUS_CACHE, "rb") as f:
            data = pickle.load(f)
        _vectorizer = data["vectorizer"]
        _tfidf_matrix = data["matrix"]
        _corpus_docs = data["docs"]
        _corpus_built_at = datetime.now(timezone.utc)
        log.info(f"[semantic] Loaded cached corpus: {len(_corpus_docs)} docs")
        return True
    except Exception as e:
        log.warning(f"[semantic] Failed to load cache: {e}")
        return False


def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    """Search the corpus using TF-IDF cosine similarity.

    Returns list of dicts with: content, source, meta, score (0-1).
    """
    # Try loading corpus
    if _vectorizer is None:
        if not _load_cache():
            # No corpus — try building on-the-fly
            count = build_corpus()
            if count == 0:
                return []

    if _vectorizer is None or _tfidf_matrix is None or _corpus_docs is None:
        return []

    try:
        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = _vectorizer.transform([query])
        scores = cosine_similarity(query_vec, _tfidf_matrix).flatten()

        # Get top_k indices
        top_indices = scores.argsort()[-top_k:][::-1]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < 0.05:  # skip very low scores
                continue
            doc = _corpus_docs[idx]
            results.append({
                "content": doc["content"],
                "source": doc["source"],
                "meta": doc.get("meta", ""),
                "score": score,
            })
        return results
    except Exception as e:
        log.error(f"[semantic] Search failed: {e}")
        return []
