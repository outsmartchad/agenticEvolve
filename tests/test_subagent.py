"""Tests for the subagent orchestrator (Phase 3)."""
import pytest
from unittest.mock import patch, MagicMock

from gateway.subagent import SubagentTask, PipelineStage, SubagentOrchestrator


class TestSubagentTask:
    def test_defaults(self):
        t = SubagentTask(name="test", prompt="do something")
        assert t.status == "pending"
        assert t.result is None
        assert t.cost == 0.0
        assert t.depends_on == []

    def test_id_generated(self):
        t1 = SubagentTask()
        t2 = SubagentTask()
        assert t1.id != t2.id
        assert len(t1.id) == 8


class TestSubagentOrchestrator:
    def setup_method(self):
        self.progress = []
        self.orch = SubagentOrchestrator(
            trace_id="test123",
            on_progress=lambda msg: self.progress.append(msg),
            config={},
            max_workers=2)

    @pytest.mark.asyncio
    async def test_run_parallel(self):
        tasks = [
            SubagentTask(name="task_a", prompt="prompt_a", model="sonnet"),
            SubagentTask(name="task_b", prompt="prompt_b", model="sonnet"),
        ]

        def mock_invoke(message, on_progress, model, session_context,
                        allowed_tools, max_seconds, config,
                        context_mode, use_workspace, **kw):
            return {"text": f"result_{model}", "cost": 0.01, "success": True}

        with patch("gateway.agent.invoke_claude_streaming",
                   side_effect=mock_invoke):
            results = await self.orch.run_parallel(tasks)

        assert len(results) == 2
        assert results[0].status == "done"
        assert results[1].status == "done"
        assert self.orch.total_cost > 0

    @pytest.mark.asyncio
    async def test_run_pipeline(self):
        stages = [
            PipelineStage(name="analyze", prompt_template="Analyze: {prev_result}"),
            PipelineStage(name="build", prompt_template="Build from: {prev_result}"),
        ]

        call_count = [0]
        def mock_invoke(message, on_progress, model, session_context,
                        allowed_tools, max_seconds, config,
                        context_mode, use_workspace, **kw):
            call_count[0] += 1
            return {"text": f"result_{call_count[0]}", "cost": 0.01, "success": True}

        with patch("gateway.agent.invoke_claude_streaming",
                   side_effect=mock_invoke):
            results = await self.orch.run_pipeline(
                stages, initial_context="initial data")

        assert len(results) == 2
        assert results[0].status == "done"
        assert results[1].status == "done"
        # Second stage should have received {prev_result} replaced
        assert "result_1" in results[1].prompt or "Build from:" in results[1].prompt

    @pytest.mark.asyncio
    async def test_run_dag_simple(self):
        tasks = [
            SubagentTask(id="t1", name="first", prompt="do first"),
            SubagentTask(id="t2", name="second", prompt="use {dep:t1}",
                        depends_on=["t1"]),
        ]

        def mock_invoke(message, on_progress, model, session_context,
                        allowed_tools, max_seconds, config,
                        context_mode, use_workspace, **kw):
            return {"text": f"done", "cost": 0.01, "success": True}

        with patch("gateway.agent.invoke_claude_streaming",
                   side_effect=mock_invoke):
            results = await self.orch.run_dag(tasks)

        assert results[0].status == "done"
        assert results[1].status == "done"
        # The dependency placeholder should have been replaced
        assert "{dep:t1}" not in results[1].prompt

    @pytest.mark.asyncio
    async def test_run_dag_failed_dep(self):
        tasks = [
            SubagentTask(id="t1", name="first", prompt="do first"),
            SubagentTask(id="t2", name="second", prompt="use {dep:t1}",
                        depends_on=["t1"]),
        ]

        call_count = [0]
        def mock_invoke(message, on_progress, model, session_context,
                        allowed_tools, max_seconds, config,
                        context_mode, use_workspace, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("first task failed")
            return {"text": "done", "cost": 0.01, "success": True}

        with patch("gateway.agent.invoke_claude_streaming",
                   side_effect=mock_invoke):
            results = await self.orch.run_dag(tasks)

        assert results[0].status == "failed"
        # Second task should still run (dep failed but placeholder replaced with error msg)
        assert results[1].status == "done"

    @pytest.mark.asyncio
    async def test_empty_inputs(self):
        assert await self.orch.run_parallel([]) == []
        assert await self.orch.run_pipeline([]) == []
        assert await self.orch.run_dag([]) == []

    def test_total_cost(self):
        assert self.orch.total_cost == 0.0

    def test_shutdown(self):
        self.orch.shutdown()  # Should not raise
