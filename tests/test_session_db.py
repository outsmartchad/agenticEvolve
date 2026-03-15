"""Tests for gateway/session_db.py — pure SQLite logic, no external services."""
import json

import pytest

import gateway.session_db as sdb


# ── Table creation ────────────────────────────────────────────


class TestInitDB:
    """init_db should create all required tables and FTS indexes."""

    EXPECTED_TABLES = {"sessions", "messages", "learnings", "costs", "instincts", "user_prefs"}
    EXPECTED_FTS = {"messages_fts", "learnings_fts", "instincts_fts"}

    def test_all_tables_exist(self, db_path):
        conn = sdb._connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        names = {r["name"] for r in rows}
        for table in self.EXPECTED_TABLES:
            assert table in names, f"Missing table: {table}"

    def test_fts_tables_exist(self, db_path):
        conn = sdb._connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        names = {r["name"] for r in rows}
        for fts in self.EXPECTED_FTS:
            assert fts in names, f"Missing FTS table: {fts}"

    def test_idempotent(self, db_path):
        """Calling init_db twice should not raise."""
        sdb.init_db()
        sdb.init_db()


# ── Sessions + Messages ──────────────────────────────────────


class TestSessionsAndMessages:
    def test_create_session_and_add_messages(self, db_path):
        sid = sdb.create_session("test-sess-1", source="pytest", user_id="u1")
        assert sid == "test-sess-1"

        sdb.add_message(sid, "user", "hello world", token_count=5)
        sdb.add_message(sid, "assistant", "hi there", token_count=3)

        msgs = sdb.get_session_messages(sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello world"
        assert msgs[1]["role"] == "assistant"

    def test_session_message_count_updated(self, db_path):
        sid = sdb.create_session("test-sess-count", source="pytest")
        sdb.add_message(sid, "user", "msg1", token_count=10)
        sdb.add_message(sid, "assistant", "msg2", token_count=20)
        sdb.add_message(sid, "user", "msg3", token_count=15)

        sessions = sdb.list_sessions()
        sess = next(s for s in sessions if s["id"] == sid)
        assert sess["message_count"] == 3
        assert sess["token_count_in"] == 25  # 10 + 15
        assert sess["token_count_out"] == 20

    def test_list_sessions_by_source(self, db_path):
        sdb.create_session("s-tg-1", source="telegram")
        sdb.create_session("s-dc-1", source="discord")

        tg = sdb.list_sessions(source="telegram")
        assert len(tg) == 1
        assert tg[0]["source"] == "telegram"

    def test_set_title(self, db_path):
        sid = sdb.create_session("title-sess", source="pytest")
        sdb.set_title(sid, "My Session Title")
        sessions = sdb.list_sessions()
        sess = next(s for s in sessions if s["id"] == sid)
        assert sess["title"] == "My Session Title"

    def test_set_title_only_once(self, db_path):
        sid = sdb.create_session("title-once", source="pytest")
        sdb.set_title(sid, "First Title")
        sdb.set_title(sid, "Second Title")
        sessions = sdb.list_sessions()
        sess = next(s for s in sessions if s["id"] == sid)
        assert sess["title"] == "First Title"


# ── FTS5 search ──────────────────────────────────────────────


class TestSearchSessions:
    def test_fts_finds_matching_message(self, db_path):
        sid = sdb.create_session("fts-sess", source="pytest")
        sdb.add_message(sid, "user", "deploy kubernetes cluster on AWS")
        sdb.add_message(sid, "assistant", "here is the kubectl config")

        results = sdb.search_sessions("kubernetes")
        assert len(results) >= 1
        assert results[0]["session_id"] == sid

    def test_fts_no_match_returns_empty(self, db_path):
        sid = sdb.create_session("fts-empty", source="pytest")
        sdb.add_message(sid, "user", "hello world")

        results = sdb.search_sessions("nonexistent_xyzzy_token")
        assert results == []


# ── Learnings ────────────────────────────────────────────────


class TestLearnings:
    def test_add_and_list(self, db_path):
        lid = sdb.add_learning(
            target="github.com/foo/bar",
            target_type="repo",
            verdict="useful",
            patterns="uses TypeScript, monorepo",
            operational_benefit="speeds up CI",
            cost=0.05,
        )
        assert isinstance(lid, int)

        learnings = sdb.list_learnings()
        assert len(learnings) == 1
        assert learnings[0]["target"] == "github.com/foo/bar"
        assert learnings[0]["verdict"] == "useful"

    def test_search_learnings(self, db_path):
        sdb.add_learning(
            target="react-query",
            target_type="library",
            verdict="adopt",
            patterns="data fetching caching hooks",
        )
        sdb.add_learning(
            target="lodash",
            target_type="library",
            verdict="skip",
            patterns="utility functions underscore",
        )

        results = sdb.search_learnings("caching hooks")
        assert len(results) >= 1
        assert results[0]["target"] == "react-query"

    def test_search_learnings_no_match(self, db_path):
        sdb.add_learning(
            target="x",
            target_type="lib",
            verdict="ok",
            patterns="alpha beta gamma",
        )
        results = sdb.search_learnings("completely_unrelated_xyzzy")
        assert results == []


# ── User Preferences ────────────────────────────────────────


class TestUserPrefs:
    def test_set_and_get(self, db_path):
        sdb.set_user_pref("user1", "theme", "dark")
        assert sdb.get_user_pref("user1", "theme") == "dark"

    def test_get_default(self, db_path):
        assert sdb.get_user_pref("user1", "missing_key") is None
        assert sdb.get_user_pref("user1", "missing_key", default="fallback") == "fallback"

    def test_upsert_overwrites(self, db_path):
        sdb.set_user_pref("user1", "lang", "en")
        sdb.set_user_pref("user1", "lang", "zh")
        assert sdb.get_user_pref("user1", "lang") == "zh"

    def test_delete(self, db_path):
        sdb.set_user_pref("user1", "temp", "value")
        sdb.delete_user_pref("user1", "temp")
        assert sdb.get_user_pref("user1", "temp") is None

    def test_delete_nonexistent_key_is_noop(self, db_path):
        """Deleting a key that doesn't exist should not raise."""
        sdb.delete_user_pref("user1", "never_set")

    def test_different_users_isolated(self, db_path):
        sdb.set_user_pref("alice", "color", "red")
        sdb.set_user_pref("bob", "color", "blue")
        assert sdb.get_user_pref("alice", "color") == "red"
        assert sdb.get_user_pref("bob", "color") == "blue"


# ── Instincts ────────────────────────────────────────────────


class TestInstincts:
    def test_upsert_creates_new(self, db_path):
        rid = sdb.upsert_instinct("always run tests before committing", context="workflow")
        assert isinstance(rid, int)

        conn = sdb._connect()
        row = conn.execute("SELECT * FROM instincts WHERE id = ?", (rid,)).fetchone()
        conn.close()
        assert row["confidence"] == pytest.approx(0.3)
        assert row["seen_count"] == 1

    def test_upsert_increments_on_repeat(self, db_path):
        sdb.upsert_instinct("prefer explicit imports", context="workflow",
                            project_id="proj-a")
        sdb.upsert_instinct("prefer explicit imports", context="workflow",
                            project_id="proj-b", confidence_delta=0.1)

        conn = sdb._connect()
        row = conn.execute(
            "SELECT * FROM instincts WHERE pattern = ?",
            ("prefer explicit imports",)
        ).fetchone()
        conn.close()
        assert row["seen_count"] == 2
        assert row["confidence"] == pytest.approx(0.4)  # 0.3 + 0.1
        projects = json.loads(row["project_ids"])
        assert "proj-a" in projects
        assert "proj-b" in projects

    def test_confidence_capped_at_1(self, db_path):
        sdb.upsert_instinct("cap test pattern", context="test", confidence_delta=0.5)
        sdb.upsert_instinct("cap test pattern", context="test", confidence_delta=0.5)
        # 0.3 + 0.5 = 0.8; 0.8 + 0.5 = 1.3 → capped at 1.0
        sdb.upsert_instinct("cap test pattern", context="test", confidence_delta=0.5)

        conn = sdb._connect()
        row = conn.execute(
            "SELECT confidence FROM instincts WHERE pattern = ?",
            ("cap test pattern",)
        ).fetchone()
        conn.close()
        assert row["confidence"] == pytest.approx(1.0)

    def test_get_promotable_instincts(self, db_path):
        # Create an instinct with high confidence seen across 2 projects
        sdb.upsert_instinct("cross-project pattern", context="test",
                            project_id="p1", confidence_delta=0.3)
        sdb.upsert_instinct("cross-project pattern", context="test",
                            project_id="p2", confidence_delta=0.3)
        sdb.upsert_instinct("cross-project pattern", context="test",
                            project_id="p2", confidence_delta=0.3)
        # confidence: 0.3 + 0.3 + 0.3 + 0.3 = 1.2 → capped at 1.0

        promotable = sdb.get_promotable_instincts(min_conf=0.8, min_projects=2)
        assert len(promotable) >= 1
        assert promotable[0]["pattern"] == "cross-project pattern"


# ── Stats ────────────────────────────────────────────────────


class TestStats:
    def test_stats_returns_correct_counts(self, db_path):
        sdb.create_session("stat-s1", source="telegram")
        sdb.create_session("stat-s2", source="telegram")
        sdb.create_session("stat-s3", source="discord")

        sdb.add_message("stat-s1", "user", "hello")
        sdb.add_message("stat-s1", "assistant", "hi")
        sdb.add_message("stat-s2", "user", "yo")

        s = sdb.stats()
        assert s["total_sessions"] == 3
        assert s["total_messages"] == 3
        assert s["sources"]["telegram"] == 2
        assert s["sources"]["discord"] == 1
        assert s["db_size_mb"] >= 0

    def test_stats_empty_db(self, db_path):
        s = sdb.stats()
        assert s["total_sessions"] == 0
        assert s["total_messages"] == 0
