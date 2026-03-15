"""Tests for gateway/semantic.py — TF-IDF corpus build and search."""
import pytest
import gateway.session_db as sdb
import gateway.semantic as sem


@pytest.fixture(autouse=True)
def reset_globals(monkeypatch, tmp_path):
    """Reset semantic module globals and redirect cache + memory paths between tests."""
    monkeypatch.setattr(sem, "_vectorizer", None)
    monkeypatch.setattr(sem, "_tfidf_matrix", None)
    monkeypatch.setattr(sem, "_corpus_docs", None)
    monkeypatch.setattr(sem, "_corpus_built_at", None)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(sem, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(sem, "CORPUS_CACHE", cache_dir / "tfidf_corpus.pkl")
    # Redirect memory/user paths to tmp so real files don't pollute tests
    import pathlib
    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))


class TestBuildCorpus:
    def test_empty_db_returns_zero(self, db_path):
        count = sem.build_corpus(force=True)
        assert count == 0

    def test_builds_from_session_messages(self, db_path):
        sid = sdb.create_session("sem-test-1", source="pytest", user_id="u1")
        sdb.add_message(sid, "user", "How do I deploy a Kubernetes cluster on AWS?", token_count=10)
        sdb.add_message(sid, "assistant", "You can use eksctl to create a cluster with managed node groups.", token_count=15)

        count = sem.build_corpus(force=True)
        assert count >= 2

    def test_builds_from_learnings(self, db_path):
        sdb.add_learning(
            target="react-query",
            target_type="library",
            verdict="adopt",
            patterns="data fetching caching hooks",
            operational_benefit="simplifies server state",
        )
        sdb.add_learning(
            target="zustand",
            target_type="library",
            verdict="adopt",
            patterns="lightweight state management for React",
            operational_benefit="replaces Redux boilerplate",
        )
        count = sem.build_corpus(force=True)
        assert count >= 2

    def test_builds_from_instincts(self, db_path):
        sdb.upsert_instinct("always run lint before committing", context="workflow")
        sdb.upsert_instinct("prefer explicit imports over wildcard", context="code style")
        count = sem.build_corpus(force=True)
        assert count >= 2

    def test_skips_short_messages(self, db_path):
        sid = sdb.create_session("sem-short", source="pytest")
        sdb.add_message(sid, "user", "hi", token_count=1)
        count = sem.build_corpus(force=True)
        # "hi" is only 2 chars, below the 20-char threshold
        assert count == 0

    def test_cache_freshness_skips_rebuild(self, db_path):
        sid = sdb.create_session("sem-cache", source="pytest")
        sdb.add_message(sid, "user", "This is a sufficiently long message for corpus building", token_count=10)
        sdb.add_message(sid, "assistant", "Here is another message to ensure at least two documents", token_count=10)

        count1 = sem.build_corpus(force=True)
        assert count1 >= 2

        # Second call without force should skip (cache is fresh)
        count2 = sem.build_corpus(force=False)
        assert count2 == count1

    def test_persists_cache_to_disk(self, db_path, tmp_path):
        sid = sdb.create_session("sem-persist", source="pytest")
        sdb.add_message(sid, "user", "Testing cache persistence for the TF-IDF corpus", token_count=8)
        sdb.add_message(sid, "assistant", "The corpus should be persisted to a pickle file on disk", token_count=10)

        sem.build_corpus(force=True)
        assert sem.CORPUS_CACHE.exists()


class TestSemanticSearch:
    def test_search_returns_relevant_results(self, db_path):
        sid = sdb.create_session("sem-search", source="pytest")
        sdb.add_message(sid, "user", "Deploy kubernetes cluster using eksctl on AWS", token_count=10)
        sdb.add_message(sid, "assistant", "Configure the VPC networking for pod communication", token_count=10)
        sdb.add_message(sid, "user", "Write a Python script to parse JSON files from disk", token_count=10)

        sem.build_corpus(force=True)
        results = sem.semantic_search("kubernetes deployment", top_k=3)
        assert len(results) >= 1
        assert results[0]["score"] > 0.05
        # The kubernetes message should score higher than the Python one
        assert "kubernetes" in results[0]["content"].lower() or "eksctl" in results[0]["content"].lower()

    def test_search_empty_corpus_returns_empty(self, db_path):
        results = sem.semantic_search("anything")
        assert results == []

    def test_search_result_structure(self, db_path):
        sid = sdb.create_session("sem-struct", source="pytest")
        sdb.add_message(sid, "user", "Building a REST API with FastAPI and SQLAlchemy", token_count=10)

        sem.build_corpus(force=True)
        results = sem.semantic_search("FastAPI REST", top_k=1)
        if results:
            r = results[0]
            assert "content" in r
            assert "source" in r
            assert "meta" in r
            assert "score" in r
            assert isinstance(r["score"], float)
            assert r["source"] == "session"

    def test_search_filters_low_scores(self, db_path):
        sid = sdb.create_session("sem-low", source="pytest")
        sdb.add_message(sid, "user", "Deploy kubernetes cluster on AWS with managed nodes", token_count=10)

        sem.build_corpus(force=True)
        results = sem.semantic_search("xyzzy_completely_unrelated_gibberish_token")
        # All results should be filtered out due to low scores
        for r in results:
            assert r["score"] >= 0.05
