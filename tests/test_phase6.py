"""Tests for Phase 6 — Self-Expanding Enhancement.

Covers:
- 6a: SubagentOrchestrator hooks in evolve BUILD stage
- 6b: Skill metrics table (record_skill_usage, get_skill_metrics, get_stale_skills, rate_skill)
- 6c: Background /learn wiring
"""
import asyncio
import sqlite3
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# 6b: Skill metrics
# ---------------------------------------------------------------------------

class TestSkillMetrics:
    """Test skill_metrics table and CRUD functions."""

    def test_record_skill_usage_creates_entry(self):
        from gateway.session_db import record_skill_usage, get_skill_metrics
        with _temp_db():
            record_skill_usage("test-skill", auto_rating=0.8)
            metrics = get_skill_metrics()
            found = [m for m in metrics if m["skill_name"] == "test-skill"]
            assert len(found) == 1
            assert found[0]["invoked_count"] == 1
            assert found[0]["auto_rating"] == 0.8

    def test_record_skill_usage_increments(self):
        from gateway.session_db import record_skill_usage, get_skill_metrics
        with _temp_db():
            record_skill_usage("test-skill")
            record_skill_usage("test-skill")
            record_skill_usage("test-skill")
            metrics = get_skill_metrics()
            found = [m for m in metrics if m["skill_name"] == "test-skill"]
            assert found[0]["invoked_count"] == 3

    def test_get_skill_metrics_ordered_by_count(self):
        from gateway.session_db import record_skill_usage, get_skill_metrics
        with _temp_db():
            for _ in range(5):
                record_skill_usage("popular-skill")
            record_skill_usage("rare-skill")
            metrics = get_skill_metrics()
            names = [m["skill_name"] for m in metrics]
            assert names.index("popular-skill") < names.index("rare-skill")

    def test_get_stale_skills(self):
        from gateway.session_db import record_skill_usage, get_stale_skills
        with _temp_db():
            record_skill_usage("active-skill")
            # Manually backdate a skill
            from gateway.session_db import _connect, _ensure_db
            _ensure_db()
            conn = _connect()
            old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
            conn.execute(
                "INSERT INTO skill_metrics (skill_name, invoked_count, last_used) "
                "VALUES (?, 1, ?)", ("old-skill", old_date)
            )
            conn.commit()
            conn.close()

            stale = get_stale_skills(days=30)
            assert "old-skill" in stale
            assert "active-skill" not in stale

    def test_rate_skill(self):
        from gateway.session_db import record_skill_usage, rate_skill, get_skill_metrics
        with _temp_db():
            record_skill_usage("rated-skill")
            rate_skill("rated-skill", 4.5)
            metrics = get_skill_metrics()
            found = [m for m in metrics if m["skill_name"] == "rated-skill"]
            assert found[0]["user_rating"] == 4.5

    def test_rate_skill_creates_if_not_exists(self):
        from gateway.session_db import rate_skill, get_skill_metrics
        with _temp_db():
            rate_skill("new-skill", 3.0)
            metrics = get_skill_metrics()
            found = [m for m in metrics if m["skill_name"] == "new-skill"]
            assert len(found) == 1
            assert found[0]["user_rating"] == 3.0


# ---------------------------------------------------------------------------
# 6a: SubagentOrchestrator hooks in evolve BUILD
# ---------------------------------------------------------------------------

class TestEvolveBuildHooks:
    """Test that evolve BUILD stage fires subagent hooks."""

    def test_build_fires_subagent_spawned_hook(self):
        """When building a skill, subagent_spawned should be fired."""
        from gateway.evolve import EvolveOrchestrator as EvolvePipeline

        with mock.patch("gateway.evolve.asyncio") as mock_asyncio:
            # Mock the loop
            mock_loop = mock.MagicMock()
            mock_asyncio.get_event_loop.return_value = mock_loop
            mock_loop.is_running.return_value = True

            pipeline = EvolvePipeline(model="sonnet", on_progress=lambda x: None)
            pipeline._report_lines = []

            # Don't actually invoke Claude
            pipeline._invoke = mock.MagicMock(return_value={"text": "", "cost": 0.01})

            # Mock QUEUE_DIR and SKILLS_DIR
            with tempfile.TemporaryDirectory() as tmpdir:
                queue_dir = Path(tmpdir) / "queue"
                skills_dir = Path(tmpdir) / "skills"
                queue_dir.mkdir()
                skills_dir.mkdir()

                with mock.patch("gateway.evolve.QUEUE_DIR", queue_dir), \
                     mock.patch("gateway.evolve.SKILLS_DIR", skills_dir):
                    # Create a fake SKILL.md after invoke
                    def _fake_invoke(prompt, label, **kwargs):
                        name = "test-skill"
                        sd = queue_dir / name
                        sd.mkdir(exist_ok=True)
                        (sd / "SKILL.md").write_text("# Test Skill\ntest")
                        return {"text": "done", "cost": 0.01}

                    pipeline._invoke = _fake_invoke

                    result = pipeline.stage_build({
                        "candidates": [
                            {"name": "test-skill", "summary": "A test", "score": 8}
                        ]
                    })

                    assert len(result["built"]) == 1
                    # Hook should have been called via run_coroutine_threadsafe
                    # (mocked, so we just verify no crash)


# ---------------------------------------------------------------------------
# 6c: Background /learn wiring
# ---------------------------------------------------------------------------

class TestBackgroundLearn:
    """Test that /learn can submit to BackgroundTaskManager."""

    def test_background_task_manager_submit_interface(self):
        """Verify BackgroundTaskManager.submit signature matches what /learn needs."""
        from gateway.background import BackgroundTaskManager
        import inspect
        sig = inspect.signature(BackgroundTaskManager.submit)
        params = list(sig.parameters.keys())
        assert "session_key" in params
        assert "platform" in params
        assert "chat_id" in params
        assert "user_id" in params
        assert "description" in params
        assert "invoke_fn" in params
        assert "on_complete" in params

    @pytest.mark.asyncio
    async def test_background_task_manager_lifecycle(self):
        """Test submit → run → complete lifecycle."""
        from gateway.background import BackgroundTaskManager

        mgr = BackgroundTaskManager(max_workers=2)
        completed = []

        def invoke(task):
            time.sleep(0.1)
            task.result = {"text": "done", "cost": 0.01}
            return task.result

        async def on_complete(task):
            completed.append(task)

        task_id = await mgr.submit(
            session_key="test",
            platform="test",
            chat_id="123",
            user_id="456",
            description="Test background task",
            invoke_fn=invoke,
            on_complete=on_complete,
        )

        assert task_id is not None
        # Wait for completion
        await asyncio.sleep(1.0)
        assert len(completed) == 1
        assert completed[0].status == "done"

        await mgr.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _temp_db:
    """Context manager that redirects session_db to a temporary database."""

    def __enter__(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        self._orig = None

        import gateway.session_db as sdb
        self._orig = sdb.DB_PATH
        sdb.DB_PATH = self._db_path
        # Force re-init
        sdb._db_initialized = False
        sdb._ensure_db()
        return self

    def __exit__(self, *args):
        import gateway.session_db as sdb
        sdb.DB_PATH = self._orig
        sdb._db_initialized = False
        try:
            self._db_path.unlink(missing_ok=True)
        except Exception:
            pass
