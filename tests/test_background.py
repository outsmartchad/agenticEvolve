"""Tests for the background task manager (Phase 3)."""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.background import BackgroundTask, BackgroundTaskManager


class TestBackgroundTask:
    def test_defaults(self):
        t = BackgroundTask(
            id="abc123", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="test task")
        assert t.status == "queued"
        assert t.result is None
        assert t.error is None

    def test_elapsed(self):
        t = BackgroundTask(
            id="abc123", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="test",
            created_at=100.0, started_at=100.0)
        t.completed_at = 110.0
        assert t.elapsed == 10.0

    def test_elapsed_str_seconds(self):
        t = BackgroundTask(
            id="abc123", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="test",
            created_at=100.0, started_at=100.0)
        t.completed_at = 145.0
        assert t.elapsed_str == "45s"

    def test_elapsed_str_minutes(self):
        t = BackgroundTask(
            id="abc123", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="test",
            created_at=100.0, started_at=100.0)
        t.completed_at = 200.0
        assert t.elapsed_str == "1m40s"

    def test_to_summary(self):
        t = BackgroundTask(
            id="abc12345", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="test task",
            status="running",
            created_at=100.0, started_at=100.0)
        t.completed_at = 110.0
        summary = t.to_summary()
        assert "abc12345" in summary
        assert "test task" in summary


class TestBackgroundTaskManager:
    @pytest.mark.asyncio
    async def test_submit_and_complete(self):
        mgr = BackgroundTaskManager(max_workers=2)
        callback = AsyncMock()

        def invoke_fn(task):
            task.result = {"text": "done", "cost": 0.01}
            return task.result

        with patch("gateway.background.BackgroundTaskManager._run_task",
                   side_effect=invoke_fn):
            task_id = await mgr.submit(
                session_key="tg:123", platform="telegram",
                chat_id="123", user_id="456",
                description="test task",
                invoke_fn=invoke_fn,
                on_complete=callback)

        assert task_id is not None
        task = mgr.get_task(task_id)
        assert task is not None
        await mgr.shutdown()

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        mgr = BackgroundTaskManager()
        # Manually add tasks for testing
        t1 = BackgroundTask(
            id="task1", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="first",
            status="done", created_at=100.0)
        t2 = BackgroundTask(
            id="task2", session_key="tg:123",
            platform="telegram", chat_id="123",
            user_id="456", description="second",
            status="running", created_at=200.0)
        mgr._tasks["task1"] = t1
        mgr._tasks["task2"] = t2

        all_tasks = mgr.list_tasks()
        assert len(all_tasks) == 2
        assert all_tasks[0].id == "task2"  # Most recent first

        active = mgr.list_tasks(include_completed=False)
        assert len(active) == 1
        assert active[0].id == "task2"

        await mgr.shutdown()

    @pytest.mark.asyncio
    async def test_active_count(self):
        mgr = BackgroundTaskManager()
        assert mgr.active_count() == 0

        t1 = BackgroundTask(
            id="t1", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="running")
        t2 = BackgroundTask(
            id="t2", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="done")
        mgr._tasks["t1"] = t1
        mgr._tasks["t2"] = t2
        assert mgr.active_count() == 1
        await mgr.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        mgr = BackgroundTaskManager()
        t = BackgroundTask(
            id="t1", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="running")
        mgr._tasks["t1"] = t

        cancelled = await mgr.cancel("t1")
        assert cancelled
        assert t.status == "cancelled"
        assert t.completed_at is not None
        await mgr.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_completed_fails(self):
        mgr = BackgroundTaskManager()
        t = BackgroundTask(
            id="t1", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="done")
        mgr._tasks["t1"] = t

        cancelled = await mgr.cancel("t1")
        assert not cancelled
        await mgr.shutdown()

    @pytest.mark.asyncio
    async def test_capacity_limit(self):
        mgr = BackgroundTaskManager(max_workers=1)

        # Add a running task
        t = BackgroundTask(
            id="t1", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="running")
        mgr._tasks["t1"] = t

        # Two more running tasks
        t2 = BackgroundTask(
            id="t2", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="running")
        t3 = BackgroundTask(
            id="t3", session_key="s", platform="t",
            chat_id="c", user_id="u", description="d",
            status="queued")
        mgr._tasks["t2"] = t2
        mgr._tasks["t3"] = t3

        # Should reject since we're at capacity (3 > max_workers=1,
        # but MAX_BACKGROUND_TASKS is the real limit)
        from gateway.background import MAX_BACKGROUND_TASKS
        # Manually set enough running to hit limit
        for i in range(MAX_BACKGROUND_TASKS):
            ti = BackgroundTask(
                id=f"cap_{i}", session_key="s", platform="t",
                chat_id="c", user_id="u", description="d",
                status="running")
            mgr._tasks[f"cap_{i}"] = ti

        result = await mgr.submit(
            session_key="s", platform="t", chat_id="c",
            user_id="u", description="overflow",
            invoke_fn=lambda t: None,
            on_complete=AsyncMock())
        assert result is None  # Rejected
        await mgr.shutdown()
