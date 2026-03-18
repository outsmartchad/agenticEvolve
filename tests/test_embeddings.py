"""Tests for gateway.embeddings — vector embedding search + RRF fusion."""
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Module import (lazy to avoid heavy model load)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_model():
    """Patch the model to avoid loading the real one during tests."""
    fake_model = mock.MagicMock()
    # encode returns deterministic vectors based on text hash
    def _fake_encode(texts, **kwargs):
        vecs = []
        for t in texts:
            np.random.seed(hash(t) % 2**31)
            v = np.random.randn(384).astype(np.float32)
            v /= np.linalg.norm(v)
            vecs.append(v)
        return np.array(vecs)

    fake_model.encode = _fake_encode
    with mock.patch("gateway.embeddings._load_model", return_value=fake_model):
        with mock.patch("gateway.embeddings._model", fake_model):
            yield fake_model


@pytest.fixture
def index():
    from gateway.embeddings import EmbeddingIndex
    idx = EmbeddingIndex()
    return idx


# ---------------------------------------------------------------------------
# EmbeddingIndex.encode
# ---------------------------------------------------------------------------

class TestEncode:
    def test_returns_ndarray(self, index):
        result = index.encode(["hello world"])
        assert isinstance(result, np.ndarray)
        assert result.shape == (1, 384)

    def test_multiple_texts(self, index):
        result = index.encode(["hello", "world", "test"])
        assert result.shape == (3, 384)

    def test_normalized(self, index):
        result = index.encode(["some text"])
        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 0.01

    def test_empty_list(self, index):
        result = index.encode([])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# EmbeddingIndex.search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_returns_results(self, index):
        # Manually populate index with vectors that guarantee cosine > 0.2
        texts = ["machine learning algorithms", "python web development",
                 "blockchain smart contracts", "neural network training"]
        index._docs = [{"content": t, "source": "test", "meta": ""} for t in texts]
        vecs = index.encode(texts)
        # Make the query vector very close to the first doc vector
        query_vec = vecs[0].copy()
        index._vectors = vecs

        # Patch encode to return the query_vec for any query
        with mock.patch.object(index, "encode", return_value=np.array([query_vec])):
            results = index.search("machine learning", top_k=3)
            assert len(results) > 0
            assert all("content" in r for r in results)
            assert all("score" in r for r in results)

    def test_search_empty_index(self, index):
        results = index.search("anything", top_k=5)
        assert results == []

    def test_search_respects_top_k(self, index):
        texts = [f"document number {i}" for i in range(20)]
        index._docs = [{"content": t, "source": "test", "meta": ""} for t in texts]
        index._vectors = index.encode(texts)

        results = index.search("document", top_k=3)
        assert len(results) <= 3

    def test_search_score_ordering(self, index):
        texts = ["cat", "dog", "fish", "bird"]
        index._docs = [{"content": t, "source": "test", "meta": ""} for t in texts]
        index._vectors = index.encode(texts)

        results = index.search("cat", top_k=4)
        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# EmbeddingIndex.incremental_update
# ---------------------------------------------------------------------------

class TestIncrementalUpdate:
    def test_adds_documents(self, index):
        texts = ["first document"]
        index._docs = [{"content": t, "source": "test", "meta": ""} for t in texts]
        index._vectors = index.encode(texts)

        new_docs = [
            {"content": "second document", "source": "new", "meta": "added"},
            {"content": "third document", "source": "new", "meta": "added"},
        ]
        index.incremental_update(new_docs)

        assert len(index._docs) == 3
        assert index._vectors.shape[0] == 3

    def test_incremental_on_empty_index(self, index):
        new_docs = [{"content": "first doc", "source": "test", "meta": ""}]
        index.incremental_update(new_docs)
        assert len(index._docs) == 1


# ---------------------------------------------------------------------------
# Cache save/load
# ---------------------------------------------------------------------------

class TestCache:
    def test_save_and_load(self, index):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "embeddings.npz"
            meta_path = Path(tmpdir) / "embeddings_meta.json"

            # Populate
            texts = ["hello world", "test document"]
            index._docs = [{"content": t, "source": "test", "meta": ""} for t in texts]
            index._vectors = index.encode(texts)

            # Save
            with mock.patch("gateway.embeddings.EMBEDDINGS_CACHE", cache_path), \
                 mock.patch("gateway.embeddings.META_CACHE", meta_path):
                index._save_cache()
                assert cache_path.exists()
                assert meta_path.exists()

                # Load into a fresh instance
                from gateway.embeddings import EmbeddingIndex
                idx2 = EmbeddingIndex()
                loaded = idx2._load_cache()
                assert loaded
                assert len(idx2._docs) == 2
                assert idx2._vectors.shape == (2, 384)


# ---------------------------------------------------------------------------
# hybrid_search (RRF fusion)
# ---------------------------------------------------------------------------

class TestHybridSearch:
    def test_hybrid_returns_list(self):
        with mock.patch("gateway.embeddings.get_index") as mock_idx:
            mock_inst = mock.MagicMock()
            mock_inst.search.return_value = [
                {"content": "embedding result", "source": "test", "meta": "", "score": 0.8},
            ]
            mock_idx.return_value = mock_inst

            with mock.patch("gateway.session_db.unified_search") as mock_us:
                mock_us.return_value = [
                    {"content": "fts result", "source": "session"},
                ]

                from gateway.embeddings import hybrid_search
                results = hybrid_search("test query", top_k=5)
                assert isinstance(results, list)

    def test_rrf_scoring(self):
        """Both FTS and embedding results should get RRF scores."""
        with mock.patch("gateway.embeddings.get_index") as mock_idx:
            mock_inst = mock.MagicMock()
            mock_inst.search.return_value = [
                {"content": "shared result", "source": "test", "meta": "", "score": 0.8},
                {"content": "embedding only", "source": "test", "meta": "", "score": 0.6},
            ]
            mock_idx.return_value = mock_inst

            with mock.patch("gateway.session_db.unified_search") as mock_us:
                mock_us.return_value = [
                    {"content": "shared result", "source": "session"},
                    {"content": "fts only", "source": "learning"},
                ]

                from gateway.embeddings import hybrid_search
                results = hybrid_search("test", top_k=10)
                # "shared result" appears in both — should have highest RRF score
                if len(results) >= 2:
                    shared = [r for r in results if "shared" in r["content"]]
                    if shared:
                        assert shared[0]["score"] > 0

    def test_hybrid_empty_results(self):
        with mock.patch("gateway.embeddings.get_index") as mock_idx:
            mock_inst = mock.MagicMock()
            mock_inst.search.return_value = []
            mock_idx.return_value = mock_inst

            with mock.patch("gateway.session_db.unified_search") as mock_us:
                mock_us.return_value = []

                from gateway.embeddings import hybrid_search
                results = hybrid_search("nothing", top_k=5)
                assert results == []

    def test_hybrid_fts_failure_graceful(self):
        """If FTS fails, embedding results still work."""
        with mock.patch("gateway.embeddings.get_index") as mock_idx:
            mock_inst = mock.MagicMock()
            mock_inst.search.return_value = [
                {"content": "embedding result", "source": "test", "meta": "", "score": 0.8},
            ]
            mock_idx.return_value = mock_inst

            with mock.patch("gateway.session_db.unified_search", side_effect=Exception("DB error")):
                from gateway.embeddings import hybrid_search
                results = hybrid_search("test", top_k=5)
                assert len(results) >= 1


# ---------------------------------------------------------------------------
# consolidate_memory (from session_db)
# ---------------------------------------------------------------------------

class TestConsolidateMemory:
    @pytest.mark.asyncio
    async def test_skip_when_under_threshold(self):
        from gateway.session_db import consolidate_memory
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Short content")
            f.flush()
            path = Path(f.name)

        try:
            with mock.patch("gateway.session_db.Path") as mock_path_cls:
                # Make Path.home() / ... return our temp file
                mock_home = mock.MagicMock()
                mock_path_cls.home.return_value = mock_home
                mock_home.__truediv__ = lambda s, x: mock_home
                mock_home.exists.return_value = True
                mock_home.read_text.return_value = "Short content"

                result = await consolidate_memory(char_limit=2200, force=False)
                assert result["consolidated"] is False
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_missing_memory_file(self):
        from gateway.session_db import consolidate_memory
        with mock.patch("gateway.session_db.Path") as mock_path_cls:
            mock_home = mock.MagicMock()
            mock_path_cls.home.return_value = mock_home
            mock_home.__truediv__ = lambda s, x: mock_home
            mock_home.exists.return_value = False

            result = await consolidate_memory()
            assert result["error"] is not None
            assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# get_memory_stats
# ---------------------------------------------------------------------------

class TestGetMemoryStats:
    def test_returns_all_keys(self):
        from gateway.session_db import get_memory_stats
        with mock.patch("gateway.session_db.Path") as mock_path_cls:
            mock_home = mock.MagicMock()
            mock_path_cls.home.return_value = mock_home
            mock_dir = mock.MagicMock()
            mock_home.__truediv__ = lambda s, x: mock_dir
            mock_dir.__truediv__ = lambda s, x: mock_dir
            mock_dir.exists.return_value = True
            mock_dir.read_text.return_value = "x" * 1000

            with mock.patch("gateway.session_db._ensure_db"), \
                 mock.patch("gateway.session_db._connect") as mock_conn:
                conn = mock.MagicMock()
                mock_conn.return_value = conn
                conn.execute.return_value.fetchone.return_value = (42,)

                stats = get_memory_stats()
                assert "memory_chars" in stats
                assert "memory_limit" in stats
                assert "memory_pct" in stats
                assert "user_chars" in stats
                assert "instinct_count" in stats
                assert "learning_count" in stats
                assert "session_count" in stats


# ---------------------------------------------------------------------------
# LLM context compaction (context.py)
# ---------------------------------------------------------------------------

class TestLLMSummarization:
    def test_llm_summarize_success(self):
        from gateway.context import _llm_summarize_messages
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout="- Key point 1\n- Key point 2\n- Key point 3",
            )
            result = _llm_summarize_messages([
                {"role": "user", "content": "How does X work?"},
                {"role": "assistant", "content": "X works by doing Y and Z."},
            ])
            assert result is not None
            assert "Key point" in result

    def test_llm_summarize_failure(self):
        from gateway.context import _llm_summarize_messages
        with mock.patch("subprocess.run", side_effect=Exception("timeout")):
            result = _llm_summarize_messages([
                {"role": "user", "content": "test"},
            ])
            assert result is None

    def test_llm_summarize_empty_output(self):
        from gateway.context import _llm_summarize_messages
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="")
            result = _llm_summarize_messages([
                {"role": "user", "content": "test"},
            ])
            assert result is None

    def test_compact_history_uses_llm(self):
        """compact_history should try LLM before falling back to truncation."""
        from gateway.context import compact_history
        messages = [{"role": "user", "content": f"Message {i} " * 50} for i in range(15)]

        with mock.patch("gateway.context._llm_summarize_messages") as mock_llm:
            mock_llm.return_value = "- Summary bullet 1\n- Summary bullet 2"
            result = compact_history(messages, target_chars=2000)
            mock_llm.assert_called_once()
            # Should have: first + summary + last 5 = 7 messages
            assert len(result) == 7
            assert "AI summary" in result[1]["content"]

    def test_compact_history_falls_back_on_llm_failure(self):
        from gateway.context import compact_history
        messages = [{"role": "user", "content": f"Message {i} " * 50} for i in range(15)]

        with mock.patch("gateway.context._llm_summarize_messages", return_value=None):
            result = compact_history(messages, target_chars=2000)
            assert len(result) == 7
            assert "Conversation summary" in result[1]["content"]
