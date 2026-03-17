"""Subagent orchestrator — generalized multi-Claude execution.

Provides three execution patterns:
  1. run_parallel — run N tasks concurrently (like evolve BUILD stage)
  2. run_pipeline — run stages sequentially, passing context forward
  3. run_dag     — execute a dependency graph with topological ordering

All patterns support:
  - Per-task model selection
  - Per-task tool allowlists
  - Isolated workspaces
  - Progress callbacks
  - Cost tracking
  - Hook integration (subagent_spawned, subagent_ended)
  - Audit logging

Generalizes the patterns from evolve.py and absorb.py into a reusable
orchestration layer.
"""
import asyncio
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from threading import BoundedSemaphore
from typing import Callable, Literal, Optional

log = logging.getLogger("agenticEvolve.subagent")


@dataclass
class SubagentTask:
    """A single unit of work for a subagent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    prompt: str = ""
    model: str = "sonnet"
    allowed_tools: list[str] | None = None
    context_mode: str | None = None
    use_workspace: bool = False
    max_seconds: int = 300
    session_context: str = ""
    depends_on: list[str] = field(default_factory=list)  # task IDs

    # Filled after execution
    result: Optional[dict] = None
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    cost: float = 0.0
    elapsed: float = 0.0
    error: Optional[str] = None


@dataclass
class PipelineStage:
    """A stage in a sequential pipeline."""
    name: str
    prompt_template: str  # Can reference {prev_result} for pipeline chaining
    model: str = "sonnet"
    allowed_tools: list[str] | None = None
    context_mode: str | None = None
    use_workspace: bool = False
    max_seconds: int = 300


class SubagentOrchestrator:
    """General-purpose multi-Claude orchestration engine.

    Generalizes evolve.py's ThreadPoolExecutor + _invoke() pattern
    into a reusable component for any pipeline.
    """

    def __init__(
        self,
        trace_id: str | None = None,
        on_progress: Callable | None = None,
        config: dict | None = None,
        max_workers: int = 3,
    ):
        self.trace_id = trace_id or str(uuid.uuid4())[:12]
        self.on_progress = on_progress or (lambda msg: None)
        self.config = config or {}
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"subagent-{self.trace_id[:6]}")
        self._semaphore = BoundedSemaphore(max_workers)
        self._total_cost = 0.0
        self._completed: list[SubagentTask] = []

    def _invoke_task(self, task: SubagentTask,
                     session_context: str = "") -> dict:
        """Execute a single subagent task (runs in thread pool)."""
        from .agent import invoke_claude_streaming

        task.status = "running"
        start = time.monotonic()

        # Fire hook
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._fire_spawned(task), loop)
        except Exception:
            pass

        self.on_progress(f"[{task.name or task.id}] Starting ({task.model})...")

        try:
            self._semaphore.acquire()
            try:
                result = invoke_claude_streaming(
                    message=task.prompt,
                    on_progress=lambda msg: self.on_progress(
                        f"[{task.name or task.id}] {msg}"),
                    model=task.model,
                    session_context=task.session_context or session_context,
                    allowed_tools=task.allowed_tools,
                    max_seconds=task.max_seconds,
                    config=self.config,
                    context_mode=task.context_mode,
                    use_workspace=task.use_workspace,
                )
            finally:
                self._semaphore.release()

            task.result = result
            task.cost = result.get("cost", 0.0)
            task.status = "done"
            task.elapsed = time.monotonic() - start
            self._total_cost += task.cost

            self.on_progress(
                f"[{task.name or task.id}] Done ({task.elapsed:.1f}s, "
                f"${task.cost:.4f})")

            # Fire hook
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._fire_ended(task), loop)
            except Exception:
                pass

            return result

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.elapsed = time.monotonic() - start
            log.error(f"Subagent task {task.id} failed: {e}")
            self.on_progress(f"[{task.name or task.id}] FAILED: {e}")
            return {"text": "", "cost": 0, "success": False}

    async def _fire_spawned(self, task: SubagentTask):
        """Fire subagent_spawned hook."""
        try:
            from .hooks import hooks
            await hooks.fire_void("subagent_spawned",
                                  task_id=task.id, model=task.model,
                                  stage=task.name)
        except Exception:
            pass

    async def _fire_ended(self, task: SubagentTask):
        """Fire subagent_ended hook."""
        try:
            from .hooks import hooks
            await hooks.fire_void("subagent_ended",
                                  task_id=task.id, outcome=task.status,
                                  cost=task.cost)
        except Exception:
            pass

    async def run_parallel(self, tasks: list[SubagentTask],
                           session_context: str = "") -> list[SubagentTask]:
        """Run multiple subagent tasks concurrently.

        Like evolve's BUILD stage but generalized.
        All tasks run simultaneously up to max_workers concurrency.

        Returns:
            The input tasks with .result, .status, .cost filled.
        """
        if not tasks:
            return []

        loop = asyncio.get_running_loop()
        self.on_progress(f"Running {len(tasks)} subagents in parallel "
                        f"(max {self._max_workers} concurrent)...")

        futures: list[tuple[SubagentTask, Future]] = []
        for task in tasks:
            fut = loop.run_in_executor(
                self._executor,
                self._invoke_task, task, session_context)
            futures.append((task, fut))

        # Wait for all
        for task, fut in futures:
            try:
                await fut
            except Exception as e:
                if task.status != "failed":
                    task.status = "failed"
                    task.error = str(e)

        self._completed.extend(tasks)
        self.on_progress(
            f"Parallel batch complete: {sum(1 for t in tasks if t.status == 'done')}"
            f"/{len(tasks)} succeeded, total cost=${self._total_cost:.4f}")
        return tasks

    async def run_pipeline(self, stages: list[PipelineStage],
                           initial_context: str = "",
                           session_context: str = "") -> list[SubagentTask]:
        """Run stages sequentially, passing context forward.

        Like evolve's stage_collect → stage_analyze → ... pattern.
        Each stage's prompt_template can reference {prev_result} to get
        the previous stage's output.

        Returns:
            A list of SubagentTasks (one per stage) with results.
        """
        if not stages:
            return []

        prev_result = initial_context
        tasks: list[SubagentTask] = []
        loop = asyncio.get_running_loop()

        for i, stage in enumerate(stages):
            self.on_progress(
                f"Pipeline stage {i+1}/{len(stages)}: {stage.name}")

            # Build prompt with context from previous stage
            prompt = stage.prompt_template.replace("{prev_result}", prev_result)

            task = SubagentTask(
                name=stage.name,
                prompt=prompt,
                model=stage.model,
                allowed_tools=stage.allowed_tools,
                context_mode=stage.context_mode,
                use_workspace=stage.use_workspace,
                max_seconds=stage.max_seconds,
                session_context=session_context,
            )

            # Run in executor (sequential)
            await loop.run_in_executor(
                self._executor,
                self._invoke_task, task, session_context)

            tasks.append(task)

            if task.status == "done" and task.result:
                prev_result = task.result.get("text", "")
            else:
                self.on_progress(
                    f"Pipeline stopped: stage '{stage.name}' failed")
                break

        self._completed.extend(tasks)
        self.on_progress(
            f"Pipeline complete: {sum(1 for t in tasks if t.status == 'done')}"
            f"/{len(stages)} stages, total cost=${self._total_cost:.4f}")
        return tasks

    async def run_dag(self, tasks: list[SubagentTask],
                      session_context: str = "") -> list[SubagentTask]:
        """Execute a dependency DAG with topological ordering.

        Tasks declare dependencies via depends_on (list of task IDs).
        Tasks with no unresolved dependencies run in parallel.
        A task's prompt can reference {dep:<task_id>} to get dependency output.

        Returns:
            All tasks with results, in original order.
        """
        if not tasks:
            return []

        # Build adjacency and in-degree
        task_map = {t.id: t for t in tasks}
        in_degree = {t.id: len(t.depends_on) for t in tasks}
        dependents: dict[str, list[str]] = {t.id: [] for t in tasks}
        for t in tasks:
            for dep_id in t.depends_on:
                if dep_id in dependents:
                    dependents[dep_id].append(t.id)

        completed_results: dict[str, str] = {}
        loop = asyncio.get_running_loop()

        self.on_progress(f"DAG execution: {len(tasks)} tasks, "
                        f"{sum(in_degree.values())} dependencies")

        while True:
            # Find ready tasks (in_degree == 0, not yet started)
            ready = [tid for tid, deg in in_degree.items()
                     if deg == 0 and task_map[tid].status == "pending"]
            if not ready:
                break

            # Inject dependency results into prompts
            batch = []
            for tid in ready:
                task = task_map[tid]
                prompt = task.prompt
                for dep_id in task.depends_on:
                    placeholder = f"{{dep:{dep_id}}}"
                    result_text = completed_results.get(dep_id, "[dependency failed]")
                    prompt = prompt.replace(placeholder, result_text)
                task.prompt = prompt
                batch.append(task)

            # Run batch in parallel
            futures = []
            for task in batch:
                fut = loop.run_in_executor(
                    self._executor,
                    self._invoke_task, task, session_context)
                futures.append((task, fut))

            for task, fut in futures:
                try:
                    await fut
                except Exception as e:
                    if task.status != "failed":
                        task.status = "failed"
                        task.error = str(e)

                # Update dependents
                if task.status == "done" and task.result:
                    completed_results[task.id] = task.result.get("text", "")
                for dep_tid in dependents.get(task.id, []):
                    in_degree[dep_tid] -= 1

            # Remove processed from in_degree
            for tid in ready:
                in_degree.pop(tid, None)

        # Mark unreachable tasks as skipped
        for t in tasks:
            if t.status == "pending":
                t.status = "skipped"

        self._completed.extend(tasks)
        self.on_progress(
            f"DAG complete: {sum(1 for t in tasks if t.status == 'done')}"
            f"/{len(tasks)} tasks succeeded, total cost=${self._total_cost:.4f}")
        return tasks

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def shutdown(self):
        """Shut down the thread pool."""
        self._executor.shutdown(wait=False)
