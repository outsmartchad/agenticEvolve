"""Proactive heartbeat system -- periodic health checks with user notification."""

import asyncio
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger("agenticEvolve.heartbeat")

HEARTBEAT_PATH = Path.home() / ".agenticEvolve" / "HEARTBEAT.md"


class HeartbeatRunner:
    def __init__(self, config: dict, notify_fn=None):
        self.interval_minutes = config.get("interval_minutes", 30)
        self.quiet_hours = config.get("quiet_hours", [0, 7])  # [start, end] in local hour
        self.notify_fn = notify_fn  # async fn(message: str)
        self.enabled = config.get("enabled", False)
        self._consecutive_failures = 0
        self._max_failures = 3
        self._task: asyncio.Task | None = None

    async def start(self):
        if not self.enabled:
            log.info("Heartbeat disabled")
            return
        self._task = asyncio.create_task(self._loop())
        log.info(f"Heartbeat started (every {self.interval_minutes}m)")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while True:
            await asyncio.sleep(self.interval_minutes * 60)

            # Check quiet hours
            hour = datetime.now().hour
            start, end = self.quiet_hours
            if start <= hour < end:
                continue

            try:
                await self._check()
                self._consecutive_failures = 0
            except Exception as e:
                self._consecutive_failures += 1
                log.error(
                    f"Heartbeat check failed "
                    f"({self._consecutive_failures}/{self._max_failures}): {e}"
                )
                if self._consecutive_failures >= self._max_failures:
                    log.error("Heartbeat auto-disabled after too many failures")
                    self.enabled = False
                    return

    async def _check(self):
        """Run heartbeat checks."""
        issues = []

        # Check 1: HEARTBEAT.md checklist
        if HEARTBEAT_PATH.exists():
            content = HEARTBEAT_PATH.read_text().strip()
            if content and not self._is_empty_checklist(content):
                # Parse unchecked items
                unchecked = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip().startswith("- [ ]")
                ]
                if unchecked:
                    issues.append(f"Checklist: {len(unchecked)} unchecked items")

        # Check 2: DB size
        db_path = Path.home() / ".agenticEvolve" / "memory" / "sessions.db"
        if db_path.exists():
            size_mb = db_path.stat().st_size / (1024 * 1024)
            if size_mb > 500:
                issues.append(f"DB size: {size_mb:.0f}MB (>500MB)")

        # Check 3: MEMORY.md size
        mem_path = Path.home() / ".agenticEvolve" / "memory" / "MEMORY.md"
        if mem_path.exists():
            chars = len(mem_path.read_text())
            if chars > 2200:
                issues.append(f"MEMORY.md: {chars} chars (>2200 limit)")

        # Check 4: Error log count (last hour)
        log_path = Path.home() / ".agenticEvolve" / "logs" / "gateway.log"
        if log_path.exists():
            try:
                recent_errors = 0
                for line in log_path.read_text().splitlines()[-500:]:
                    if "ERROR" in line:
                        recent_errors += 1
                if recent_errors > 10:
                    issues.append(f"Errors: {recent_errors} in recent log (>10)")
            except Exception:
                pass

        if issues:
            msg = "Heartbeat alert:\n" + "\n".join(f"- {i}" for i in issues)
            log.warning(msg)
            if self.notify_fn:
                await self.notify_fn(msg)
        else:
            log.debug("Heartbeat: all clear")

    def _is_empty_checklist(self, content: str) -> bool:
        """Check if content is just headers and empty checkboxes."""
        for line in content.splitlines():
            line = line.strip()
            if (
                line
                and not line.startswith("#")
                and not line.startswith("- [ ]")
                and not line.startswith("<!--")
            ):
                return False
        return True
