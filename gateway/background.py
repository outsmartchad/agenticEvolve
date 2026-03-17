"""Background task manager for long-running Claude invocations.

Allows the gateway to return an immediate "working on it" response
while the Claude invocation runs in a background thread. On completion,
the result is delivered back to the originating platform via callback.

Architecture:
  1. User sends a message that triggers a long-running task
  2. Gateway submits to BackgroundTaskManager
  3. Manager returns task_id immediately
  4. Platform adapter returns "Task started, I'll notify when done"
  5. Background thread runs invoke_claude with progress tracking
  6. On completion, callback delivers result to platform
  7. Hooks fire: background_task_complete / background_task_failed

Commands:
  /tasks — list running/recent background tasks
  /cancel <task_id> — cancel a running task
"""
import asyncio
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, Optional

log = logging.getLogger("agenticEvolve.background")

# Max concurrent background tasks
MAX_BACKGROUND_TASKS = 3
# How long to keep completed tasks in history (seconds)
TASK_HISTORY_TTL = 3600  # 1 hour


@dataclass
class BackgroundTask:
    """Represents a detached long-running Claude invocation."""
    id: str
    session_key: str
    platform: str
    chat_id: str
    user_id: str
    description: str
    status: Literal["queued", "running", "done", "failed", "cancelled"] = "queued"
    progress_lines: list[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds."""
        end = self.completed_at or time.time()
        start = self.started_at or self.created_at
        return end - start

    @property
    def elapsed_str(self) -> str:
        """Human-readable elapsed time."""
        s = int(self.elapsed)
        if s < 60:
            return f"{s}s"
        return f"{s // 60}m{s % 60}s"

    def to_summary(self) -> str:
        """One-line summary for /tasks command."""
        status_icon = {
            "queued": "⏳", "running": "🔄",
            "done": "✅", "failed": "❌", "cancelled": "🚫"
        }
        icon = status_icon.get(self.status, "❓")
        return f"{icon} `{self.id[:8]}` {self.description} ({self.elapsed_str})"


class BackgroundTaskManager:
    """Manages background Claude invocations with progress tracking."""

    def __init__(self, max_workers: int = MAX_BACKGROUND_TASKS):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="bg-task")
        self._tasks: dict[str, BackgroundTask] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._on_complete_callbacks: dict[str, Callable] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        session_key: str,
        platform: str,
        chat_id: str,
        user_id: str,
        description: str,
        invoke_fn: Callable,
        on_complete: Callable,
    ) -> Optional[str]:
        """Submit a background task.

        Args:
            session_key: Session key for the originating conversation.
            platform: Platform name (telegram, whatsapp, discord).
            chat_id: Chat ID for result delivery.
            user_id: User who submitted the task.
            description: Short description of what the task does.
            invoke_fn: Callable that runs invoke_claude (blocking).
                       Receives (task: BackgroundTask) as argument.
                       Should set task.result on success.
            on_complete: Async callback(task: BackgroundTask) called on finish.
                         Used by platform adapters to deliver results.

        Returns:
            task_id if submitted, None if at capacity.
        """
        async with self._lock:
            # Check capacity
            running = sum(1 for t in self._tasks.values()
                         if t.status in ("queued", "running"))
            if running >= MAX_BACKGROUND_TASKS:
                return None

            task_id = str(uuid.uuid4())[:12]
            task = BackgroundTask(
                id=task_id,
                session_key=session_key,
                platform=platform,
                chat_id=chat_id,
                user_id=user_id,
                description=description,
            )
            self._tasks[task_id] = task
            self._on_complete_callbacks[task_id] = on_complete

        # Fire hook
        try:
            from .hooks import hooks
            await hooks.fire_void("background_task_submit",
                                  task_id=task_id, session_key=session_key,
                                  description=description)
        except Exception:
            pass

        # Submit to executor
        loop = asyncio.get_running_loop()
        fut = loop.run_in_executor(
            self._executor, self._run_task, task, invoke_fn)
        self._futures[task_id] = fut

        # Set up completion callback
        fut.add_done_callback(
            lambda f: asyncio.run_coroutine_threadsafe(
                self._on_task_done(task_id), loop))

        log.info(f"Background task submitted: {task_id} — {description}")
        return task_id

    def _run_task(self, task: BackgroundTask, invoke_fn: Callable) -> dict:
        """Execute the task in a background thread."""
        task.status = "running"
        task.started_at = time.time()

        try:
            result = invoke_fn(task)
            task.result = result
            task.status = "done"
            task.completed_at = time.time()
            log.info(f"Background task completed: {task.id} ({task.elapsed_str})")
            return result
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
            log.error(f"Background task failed: {task.id} — {e}")
            raise

    async def _on_task_done(self, task_id: str):
        """Called when a background task finishes (success or failure)."""
        task = self._tasks.get(task_id)
        if not task:
            return

        # Fire hooks
        try:
            from .hooks import hooks
            if task.status == "done":
                await hooks.fire_void("background_task_complete",
                                      task_id=task_id, result=task.result)
            elif task.status == "failed":
                await hooks.fire_void("background_task_failed",
                                      task_id=task_id, error=task.error)
        except Exception:
            pass

        # Call completion callback
        callback = self._on_complete_callbacks.pop(task_id, None)
        if callback:
            try:
                await callback(task)
            except Exception as e:
                log.error(f"Background task callback error: {task_id} — {e}")

        # Clean up future reference
        self._futures.pop(task_id, None)

        # Prune old completed tasks
        await self._prune()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running/queued background task."""
        task = self._tasks.get(task_id)
        if not task or task.status not in ("queued", "running"):
            return False

        fut = self._futures.get(task_id)
        if fut:
            fut.cancel()

        task.status = "cancelled"
        task.completed_at = time.time()
        self._futures.pop(task_id, None)
        self._on_complete_callbacks.pop(task_id, None)
        log.info(f"Background task cancelled: {task_id}")
        return True

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, include_completed: bool = True) -> list[BackgroundTask]:
        """List all tasks, most recent first."""
        tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if t.status in ("queued", "running")]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def active_count(self) -> int:
        """Number of currently running/queued tasks."""
        return sum(1 for t in self._tasks.values()
                   if t.status in ("queued", "running"))

    async def _prune(self):
        """Remove old completed tasks beyond TTL."""
        now = time.time()
        to_remove = []
        for tid, task in self._tasks.items():
            if task.status in ("done", "failed", "cancelled"):
                if task.completed_at and (now - task.completed_at) > TASK_HISTORY_TTL:
                    to_remove.append(tid)
        for tid in to_remove:
            del self._tasks[tid]

    async def shutdown(self):
        """Cancel all running tasks and shut down executor."""
        for task_id in list(self._futures.keys()):
            await self.cancel(task_id)
        self._executor.shutdown(wait=False)
        log.info("Background task manager shut down")
