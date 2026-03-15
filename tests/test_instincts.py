"""Tests for instinct upsert (context bug fix) and auto-promotion pipeline."""
import json

import pytest

import gateway.session_db as sdb


class TestUpsertInstinctContextFix:
    """Regression tests for the context column bug fix.

    The SELECT in upsert_instinct previously omitted the 'context' column,
    causing an IndexError when context arg was falsy and the code fell back
    to existing["context"].
    """

    def test_upsert_with_context_then_without(self, db_path):
        """First call provides context, second call omits it — should use existing context."""
        sdb.upsert_instinct("pattern-ctx-1", context="original context")
        # Second call with empty context — should fall back to existing["context"]
        rid = sdb.upsert_instinct("pattern-ctx-1", context="")
        assert isinstance(rid, int)

        # Verify FTS still has the original context
        conn = sdb._connect()
        fts = conn.execute(
            "SELECT context FROM instincts_fts WHERE pattern = ?",
            ("pattern-ctx-1",)
        ).fetchone()
        conn.close()
        assert fts is not None
        assert fts["context"] == "original context"

    def test_upsert_both_calls_no_context(self, db_path):
        """Both calls omit context — should not crash."""
        sdb.upsert_instinct("pattern-no-ctx")
        rid = sdb.upsert_instinct("pattern-no-ctx")
        assert isinstance(rid, int)

    def test_upsert_second_call_with_new_context_does_not_crash(self, db_path):
        """When second call provides a different context, the upsert should succeed.

        Note: upsert_instinct does NOT update the main instincts.context column
        on repeat calls — it only uses the new context for the FTS insert.
        The main table retains the original context from the INSERT.
        """
        sdb.upsert_instinct("pattern-overwrite", context="old")
        rid = sdb.upsert_instinct("pattern-overwrite", context="new")
        assert isinstance(rid, int)

        # Main table context should still be "old" (not updated on upsert)
        conn = sdb._connect()
        row = conn.execute("SELECT context FROM instincts WHERE id = ?", (rid,)).fetchone()
        conn.close()
        assert row["context"] == "old"


class TestAutoPromoteInstincts:
    """Tests for auto_promote_instincts — promoting high-confidence instincts to MEMORY.md."""

    @pytest.fixture()
    def memory_dir(self, tmp_path, monkeypatch):
        """Create a temp memory dir and redirect the MEMORY.md path."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        mem_file = mem_dir / "MEMORY.md"
        mem_file.write_text("# Memory\nSome existing content here.\n")

        # Monkeypatch Path.home to redirect memory path
        import pathlib
        original_home = pathlib.Path.home

        def fake_home():
            return tmp_path / ".agenticEvolve"

        # Create the .agenticEvolve/memory structure
        ae_dir = tmp_path / ".agenticEvolve" / "memory"
        ae_dir.mkdir(parents=True)
        ae_mem = ae_dir / "MEMORY.md"
        ae_mem.write_text("# Memory\nSome existing content here.\n")

        monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: tmp_path))
        return ae_mem

    def _make_promotable_instinct(self, pattern, n_projects=2, n_repeats=3):
        """Create an instinct that qualifies for promotion."""
        for i in range(n_repeats):
            proj = f"proj-{i % n_projects}" if i < n_projects else f"proj-{i % n_projects}"
            sdb.upsert_instinct(pattern, context="test", project_id=proj,
                                confidence_delta=0.25)

    def test_promotes_eligible_instinct(self, db_path, memory_dir):
        self._make_promotable_instinct("always validate input before processing")

        promoted = sdb.auto_promote_instincts(max_promotions=3)
        assert "always validate input before processing" in promoted

        content = memory_dir.read_text()
        assert "always validate input before processing" in content

    def test_skips_duplicate_patterns(self, db_path, memory_dir):
        # Put the pattern in MEMORY.md already
        memory_dir.write_text("# Memory\nalways validate input before processing\n")
        self._make_promotable_instinct("always validate input before processing")

        promoted = sdb.auto_promote_instincts(max_promotions=3)
        assert "always validate input before processing" not in promoted

    def test_respects_char_limit(self, db_path, memory_dir):
        # Fill memory to near limit
        memory_dir.write_text("X" * 2190)
        self._make_promotable_instinct("a very long pattern that would exceed the limit")

        promoted = sdb.auto_promote_instincts(max_promotions=3)
        assert len(promoted) == 0

    def test_no_eligible_returns_empty(self, db_path, memory_dir):
        # Low confidence instinct
        sdb.upsert_instinct("weak pattern", context="test", confidence_delta=0.01)
        promoted = sdb.auto_promote_instincts()
        assert promoted == []

    def test_max_promotions_respected(self, db_path, memory_dir):
        for i in range(5):
            self._make_promotable_instinct(f"promotable pattern number {i}")

        promoted = sdb.auto_promote_instincts(max_promotions=2)
        assert len(promoted) <= 2
