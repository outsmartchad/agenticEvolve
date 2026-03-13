"""GatewayRunner — main entry point for the agenticEvolve messaging gateway.

Connects Telegram/Discord/WhatsApp, routes messages to Claude Code,
manages sessions, runs cron scheduler.

Usage:
    python -m gateway.run
    ae gateway
"""
import asyncio
import logging
import signal
import sys
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import load_config, config_changed, reload_config
from .agent import invoke_claude, get_today_cost, generate_title, consolidate_session
from .hooks import hooks
from .session_db import (
    create_session, generate_session_id, add_message,
    end_session, list_sessions, get_session_messages, set_title
)
from .platforms.telegram import TelegramAdapter
from .platforms.discord import DiscordAdapter
from .platforms.whatsapp import WhatsAppAdapter

log = logging.getLogger("agenticEvolve.gateway")

EXODIR = Path.home() / ".agenticEvolve"
PID_FILE = EXODIR / "gateway.pid"
LOG_DIR = EXODIR / "logs"
CRON_DIR = EXODIR / "cron"
CRON_JOBS_FILE = CRON_DIR / "jobs.json"
CRON_OUTPUT_DIR = CRON_DIR / "output"


class GatewayRunner:
    """Main gateway process — routes platform messages to Claude Code."""

    def __init__(self):
        self.config: dict = {}
        self.adapters: list = []
        self._adapter_map: dict[str, object] = {}  # platform_name -> adapter
        self._active_sessions: dict[str, str] = {}  # session_key -> session_id
        self._session_last_active: dict[str, datetime] = {}  # session_key -> last msg time
        self._session_msg_count: dict[str, int] = {}  # session_key -> message count (for title)
        self._locks: dict[str, asyncio.Lock] = {}  # session_key -> lock
        self._shutdown_event = asyncio.Event()
        self._start_time = 0.0
        self._session_cleanup_task: Optional[asyncio.Task] = None
        self._cron_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._draining: bool = False
        self._inflight: set[asyncio.Future] = set()

    # ── Session key ──────────────────────────────────────────────

    def _session_key(self, platform: str, chat_id: str) -> str:
        return f"{platform}:{chat_id}"

    def _get_or_create_session(self, platform: str, chat_id: str,
                                user_id: str) -> str:
        key = self._session_key(platform, chat_id)
        idle_minutes = self.config.get("session_idle_minutes", 120)
        now = datetime.now(timezone.utc)

        if key in self._active_sessions:
            last = self._session_last_active.get(key)
            if last and (now - last) > timedelta(minutes=idle_minutes):
                old_sid = self._active_sessions.pop(key)
                end_session(old_sid)
                self._session_msg_count.pop(key, None)
                log.info(f"Session expired: {old_sid} (idle {idle_minutes}m)")
            else:
                self._session_last_active[key] = now
                return self._active_sessions[key]

        sid = generate_session_id()
        create_session(sid, source=platform, user_id=user_id,
                       model=self.config.get("model", "sonnet"))
        self._active_sessions[key] = sid
        self._session_last_active[key] = now
        self._session_msg_count[key] = 0
        log.info(f"New session: {sid} ({platform}:{chat_id})")
        return sid

    def _get_lock(self, session_key: str) -> asyncio.Lock:
        if session_key not in self._locks:
            self._locks[session_key] = asyncio.Lock()
        return self._locks[session_key]

    # ── Cost cap ─────────────────────────────────────────────────

    def _check_cost_cap(self) -> tuple[bool, str]:
        """Check if daily or weekly cost cap is exceeded. Returns (allowed, reason)."""
        from .agent import get_week_cost

        daily_cap = self.config.get("daily_cost_cap", 5.0)
        today_cost = get_today_cost()
        if today_cost >= daily_cap:
            return False, f"Daily cost cap reached (${today_cost:.2f}/${daily_cap:.2f}). Resets at midnight UTC."

        weekly_cap = self.config.get("weekly_cost_cap", 25.0)
        week_cost = get_week_cost()
        if week_cost >= weekly_cap:
            return False, f"Weekly cost cap reached (${week_cost:.2f}/${weekly_cap:.2f}). Resets Monday UTC."

        return True, ""

    # ── Message handler ──────────────────────────────────────────

    async def _tracked_invoke(self, session_id: str, text: str, model: str,
                               history: list, session_context: str,
                               cfg: dict) -> dict:
        """Invoke Claude in executor and track the future in _inflight for drain-on-shutdown."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: invoke_claude(
                text, model=model, history=history,
                session_context=session_context,
                config=cfg
            )
        )

    async def handle_message(self, platform: str, chat_id: str,
                               user_id: str, text: str) -> str:
        """Core message handler — called by platform adapters."""
        # Drain guard — reject new messages while shutting down
        if self._draining:
            log.info(f"Rejecting message during drain ({platform}:{chat_id})")
            return "Gateway is restarting, please try again in 30s."

        key = self._session_key(platform, chat_id)
        lock = self._get_lock(key)

        async with lock:
            # Hot config reload (ZeroClaw pattern — apply on next message)
            if config_changed():
                self.config, changes = reload_config()
                log.info(f"Hot-reloaded config: {changes}")

            # Cost cap check
            allowed, reason = self._check_cost_cap()
            if not allowed:
                return reason

            session_id = self._get_or_create_session(platform, chat_id, user_id)

            # Fire message_received hook (void — non-blocking)
            await hooks.fire_void("message_received",
                                  platform=platform, chat_id=chat_id, text=text)

            # Persist user message
            add_message(session_id, "user", text)

            # Track message count for title generation
            self._session_msg_count[key] = self._session_msg_count.get(key, 0) + 1

            # Auto-title on first message
            if self._session_msg_count[key] == 1:
                title = generate_title(text)
                set_title(session_id, title)

            # Fetch conversation history for this session
            history = get_session_messages(session_id)
            # Remove the last message (the one we just added) — it's the current message
            if history:
                history = history[:-1]

            # Build context
            session_context = (
                f"[Gateway: platform={platform}, chat_id={chat_id}, "
                f"user_id={user_id}, session={session_id}]"
            )

            model = self.config.get("model", "sonnet")

            # Allow before_invoke hooks to mutate the prompt
            invoke_text = await hooks.fire_modifying("before_invoke", text)

            cfg = self.config

            # Track in-flight futures for drain-on-shutdown
            fut = asyncio.ensure_future(
                self._tracked_invoke(session_id, invoke_text, model,
                                     history, session_context, cfg)
            )
            self._inflight.add(fut)
            fut.add_done_callback(self._inflight.discard)

            try:
                result = await fut
            except asyncio.CancelledError:
                return "Request cancelled during shutdown."

            response_text = result.get("text", "No response.")
            cost = result.get("cost", 0)

            # Persist assistant response
            add_message(session_id, "assistant", response_text)

            # Fire llm_output hook (void — non-blocking)
            await hooks.fire_void("llm_output",
                                  session_id=session_id, text=response_text, cost=cost)

            # Log cost
            if cost > 0:
                self._log_cost(platform, session_id, cost)
                log.info(f"Response sent ({platform}:{chat_id}) cost=${cost:.4f}")

            return response_text

    # ── Cost tracking ────────────────────────────────────────────

    def _log_cost(self, platform: str, session_id: str, cost: float,
                  pipeline: str = ""):
        """Log cost to cost.log (file) and SQLite (indexed). Dual-write for migration safety."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cost_file = LOG_DIR / "cost.log"
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts}\t{platform}\t{session_id}\t${cost:.4f}\n"
        with open(cost_file, "a") as f:
            f.write(line)
        # SQLite dual-write — O(1) indexed lookup replaces O(n) log scan
        try:
            from .session_db import log_cost as db_log_cost
            db_log_cost(cost, platform=platform, session_id=session_id,
                        pipeline=pipeline or platform)
        except Exception as e:
            log.warning(f"SQLite cost log failed (log file still written): {e}")

    # ── Session cleanup ──────────────────────────────────────────

    async def _session_cleanup_loop(self):
        idle_minutes = self.config.get("session_idle_minutes", 120)
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(60)
                now = datetime.now(timezone.utc)
                expired_keys = []
                for key, last in self._session_last_active.items():
                    if (now - last) > timedelta(minutes=idle_minutes):
                        expired_keys.append(key)
                for key in expired_keys:
                    sid = self._active_sessions.pop(key, None)
                    self._session_last_active.pop(key, None)
                    self._session_msg_count.pop(key, None)
                    self._locks.pop(key, None)
                    if sid:
                        end_session(sid)
                        log.info(f"Cleaned up idle session: {sid}")
                        # Fire silent consolidation in background thread
                        loop = asyncio.get_running_loop()
                        loop.run_in_executor(None, consolidate_session, sid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Session cleanup error: {e}")

    # ── Cron scheduler ───────────────────────────────────────────

    async def _cron_loop(self):
        """Tick-based cron scheduler. Checks jobs.json every 60s."""
        if not self.config.get("cron", {}).get("enabled", True):
            log.info("Cron scheduler: disabled")
            return

        log.info("Cron scheduler: started")
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(60)
                await self._run_due_jobs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Cron scheduler error: {e}")

    async def _run_due_jobs(self):
        """Check and execute due cron jobs."""
        if not CRON_JOBS_FILE.exists():
            return

        try:
            jobs = json.loads(CRON_JOBS_FILE.read_text())
        except (json.JSONDecodeError, Exception) as e:
            log.error(f"Failed to read jobs.json: {e}")
            return

        now = datetime.now(timezone.utc)
        modified = False

        for job in jobs:
            if job.get("paused", False):
                continue

            next_run = job.get("next_run_at")
            if not next_run:
                continue

            try:
                next_dt = datetime.fromisoformat(next_run)
            except (ValueError, TypeError):
                continue

            if now < next_dt:
                continue

            # Job is due — execute it
            job_id = job.get("id", "unknown")
            prompt = job.get("prompt", "")
            deliver_to = job.get("deliver_to", "local")
            deliver_chat_id = job.get("deliver_chat_id", "")

            log.info(f"Cron job due: {job_id}")

            # Native digest job — no Claude invocation needed
            if job_id == "daily-digest":
                adapter = self._adapter_map.get("telegram")
                if adapter and deliver_chat_id and hasattr(adapter, "_send_digest"):
                    try:
                        await adapter._send_digest(deliver_chat_id, days=1)
                        log.info("Cron: daily-digest sent")
                    except Exception as e:
                        log.error(f"Cron: daily-digest failed: {e}")
                # Update job and continue (no cost)
                job["run_count"] = job.get("run_count", 0) + 1
                job["last_run_at"] = now.isoformat()
                job["next_run_at"] = self._next_cron_run(job, now).isoformat()
                modified = True
                log.info(f"Cron job completed: {job_id} (cost=$0.0000)")
                continue

            # Cost cap check
            allowed, reason = self._check_cost_cap()
            if not allowed:
                log.warning(f"Cron job {job_id} skipped: {reason}")
                continue

            # Run in executor
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda p=prompt: invoke_claude(
                    p, model=self.config.get("model", "sonnet"),
                    session_context=f"[Cron job: {job_id}]"
                )
            )

            response = result.get("text", "No response.")
            cost = result.get("cost", 0)

            if cost > 0:
                self._log_cost("cron", job_id, cost)

            # Save output
            CRON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            job_output_dir = CRON_OUTPUT_DIR / job_id
            job_output_dir.mkdir(exist_ok=True)
            output_file = job_output_dir / f"{now.strftime('%Y%m%d_%H%M%S')}.txt"
            output_file.write_text(response)

            # Deliver to platform
            if deliver_to != "local" and deliver_chat_id:
                adapter = self._adapter_map.get(deliver_to)
                if adapter:
                    try:
                        await adapter.send(deliver_chat_id, f"[Cron: {job_id}]\n\n{response}")
                    except Exception as e:
                        log.error(f"Cron delivery failed ({deliver_to}): {e}")

            # Update job
            job["run_count"] = job.get("run_count", 0) + 1
            job["last_run_at"] = now.isoformat()

            # Compute next run
            schedule_type = job.get("schedule_type", "")
            if schedule_type == "once":
                job["paused"] = True
            elif schedule_type == "interval":
                interval_seconds = job.get("interval_seconds", 3600)
                job["next_run_at"] = (now + timedelta(seconds=interval_seconds)).isoformat()
            elif schedule_type == "cron":
                job["next_run_at"] = self._next_cron_run(job, now).isoformat()

            modified = True
            log.info(f"Cron job completed: {job_id} (cost=${cost:.4f})")

        if modified:
            try:
                CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))
            except Exception as e:
                log.error(f"Failed to write jobs.json: {e}")

    # ── Cron expression parser ──────────────────────────────────

    def _next_cron_run(self, job: dict, after: datetime) -> datetime:
        """Calculate next run time from a cron expression with optional timezone.

        Supports standard 5-field cron: minute hour day month weekday
        Handles *, specific values, and */N step syntax.
        Falls back to +24h if parsing fails.
        """
        cron_expr = job.get("cron", "")
        tz_name = job.get("timezone", "")

        # Resolve timezone offset
        tz = timezone.utc
        TZ_OFFSETS = {
            "Asia/Hong_Kong": 8, "Asia/Shanghai": 8, "Asia/Tokyo": 9,
            "US/Eastern": -5, "US/Pacific": -8, "Europe/London": 0,
            "Europe/Berlin": 1, "UTC": 0,
        }
        if tz_name in TZ_OFFSETS:
            tz = timezone(timedelta(hours=TZ_OFFSETS[tz_name]))

        if not cron_expr or len(cron_expr.split()) != 5:
            return after + timedelta(hours=24)

        try:
            parts = cron_expr.split()
            minute_spec, hour_spec = parts[0], parts[1]
            # day_spec, month_spec, weekday_spec = parts[2], parts[3], parts[4]

            def _parse_field(spec: str, max_val: int) -> list[int]:
                """Parse a cron field into a sorted list of valid values."""
                if spec == "*":
                    return list(range(max_val))
                if spec.startswith("*/"):
                    step = int(spec[2:])
                    return list(range(0, max_val, step))
                if "," in spec:
                    return sorted(int(v) for v in spec.split(","))
                return [int(spec)]

            valid_minutes = _parse_field(minute_spec, 60)
            valid_hours = _parse_field(hour_spec, 24)

            # Start searching from 1 minute after 'after', in the job's timezone
            candidate = after.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)

            # Search up to 48 hours ahead
            for _ in range(48 * 60):
                if candidate.hour in valid_hours and candidate.minute in valid_minutes:
                    return candidate.astimezone(timezone.utc)
                candidate += timedelta(minutes=1)

            # Fallback
            return after + timedelta(hours=24)

        except Exception as e:
            log.warning(f"Failed to parse cron '{cron_expr}': {e}, falling back to +24h")
            return after + timedelta(hours=24)

    # ── Platform startup ─────────────────────────────────────────

    def _create_adapters(self):
        platforms_cfg = self.config.get("platforms", {})

        adapter_classes = {
            "telegram": TelegramAdapter,
            "discord": DiscordAdapter,
            "whatsapp": WhatsAppAdapter,
        }

        for name, cls in adapter_classes.items():
            pcfg = platforms_cfg.get(name, {})
            if not pcfg.get("enabled", False):
                log.info(f"Platform {name}: disabled")
                continue
            try:
                adapter = cls(pcfg, self.handle_message)
                adapter._gateway = self  # give adapter access to gateway
                self.adapters.append(adapter)
                self._adapter_map[name] = adapter
                log.info(f"Platform {name}: created")
            except ImportError as e:
                log.warning(f"Platform {name}: skipped ({e})")
            except Exception as e:
                log.error(f"Platform {name}: failed to create ({e})")

    # ── Main lifecycle ───────────────────────────────────────────

    async def start(self):
        self.config = load_config()
        log.info("Config loaded")

        self._create_adapters()

        if not self.adapters:
            log.error("No platform adapters enabled. Configure at least one in config.yaml or .env")
            log.error("Example: set TELEGRAM_BOT_TOKEN in ~/.agenticEvolve/.env")
            return

        for adapter in self.adapters:
            try:
                await adapter.start()
            except Exception as e:
                log.error(f"Failed to start {adapter.name}: {e}")

        started = [a.name for a in self.adapters]
        log.info(f"Gateway running: {', '.join(started)}")

        PID_FILE.write_text(str(os.getpid()))
        import time
        self._start_time = time.time()

        # Start background tasks
        self._session_cleanup_task = asyncio.create_task(self._session_cleanup_loop())
        self._cron_task = asyncio.create_task(self._cron_loop())

        # Start watchdog if configured
        watchdog_cfg = self.config.get("watchdog", {})
        watchdog_chat_id = str(watchdog_cfg.get("chat_id", ""))
        if watchdog_cfg.get("enabled", False) and watchdog_chat_id:
            from .watchdog import _watchdog_loop
            self._watchdog_task = asyncio.create_task(
                _watchdog_loop(self, watchdog_chat_id, self._shutdown_event)
            )
            log.info(f"Watchdog: started (chat_id={watchdog_chat_id})")

        await self._shutdown_event.wait()

    async def stop(self):
        log.info("Gateway shutting down...")

        # Drain in-flight requests before cancelling background tasks
        self._draining = True
        if self._inflight:
            log.info(f"Draining {len(self._inflight)} in-flight requests (30s timeout)...")
            await asyncio.wait(self._inflight, timeout=30)

        for task in [self._session_cleanup_task, self._cron_task, self._watchdog_task]:
            if task:
                task.cancel()

        for adapter in self.adapters:
            try:
                await adapter.stop()
            except Exception as e:
                log.error(f"Error stopping {adapter.name}: {e}")

        for key, sid in self._active_sessions.items():
            end_session(sid)
            consolidate_session(sid)
        self._active_sessions.clear()

        if PID_FILE.exists():
            PID_FILE.unlink()

        log.info("Gateway stopped")

    def request_shutdown(self):
        self._shutdown_event.set()


# ── Entry point ──────────────────────────────────────────────────

def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    stderr_handler.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_DIR / "gateway.log")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    root = logging.getLogger("agenticEvolve")
    root.setLevel(logging.DEBUG)
    root.addHandler(stderr_handler)
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)


async def start_gateway():
    runner = GatewayRunner()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, runner.request_shutdown)

    try:
        await runner.start()
    finally:
        await runner.stop()


def main():
    setup_logging()
    log.info("Starting agenticEvolve gateway...")
    asyncio.run(start_gateway())


if __name__ == "__main__":
    main()
