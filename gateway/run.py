"""GatewayRunner — main entry point for the agenticEvolve messaging gateway.

Connects Telegram/Discord/WhatsApp, routes messages to Claude Code,
manages sessions, and (eventually) runs the cron scheduler.

Usage:
    python -m gateway.run
    ae gateway
"""
import asyncio
import logging
import signal
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import load_config
from .agent import invoke_claude
from .session_db import (
    create_session, generate_session_id, add_message,
    end_session, list_sessions, get_session_messages
)
from .platforms.telegram import TelegramAdapter
from .platforms.discord import DiscordAdapter
from .platforms.whatsapp import WhatsAppAdapter

log = logging.getLogger("agenticEvolve.gateway")

EXODIR = Path.home() / ".agenticEvolve"
PID_FILE = EXODIR / "gateway.pid"
LOG_DIR = EXODIR / "logs"


class GatewayRunner:
    """Main gateway process — routes platform messages to Claude Code."""

    def __init__(self):
        self.config: dict = {}
        self.adapters: list = []
        self._active_sessions: dict[str, str] = {}  # session_key -> session_id
        self._session_last_active: dict[str, datetime] = {}  # session_key -> last msg time
        self._locks: dict[str, asyncio.Lock] = {}  # session_key -> lock (serialize per-chat)
        self._shutdown_event = asyncio.Event()
        self._session_cleanup_task: Optional[asyncio.Task] = None

    # ── Session key ──────────────────────────────────────────────

    def _session_key(self, platform: str, chat_id: str) -> str:
        """Deterministic session key: platform:chat_id."""
        return f"{platform}:{chat_id}"

    def _get_or_create_session(self, platform: str, chat_id: str,
                                user_id: str) -> str:
        """Return active session_id, creating a new one if expired or missing."""
        key = self._session_key(platform, chat_id)
        idle_minutes = self.config.get("session_idle_minutes", 120)
        now = datetime.now(timezone.utc)

        # Check if existing session is still valid
        if key in self._active_sessions:
            last = self._session_last_active.get(key)
            if last and (now - last) > timedelta(minutes=idle_minutes):
                # Session expired — end it and create new
                old_sid = self._active_sessions.pop(key)
                end_session(old_sid)
                log.info(f"Session expired: {old_sid} (idle {idle_minutes}m)")
            else:
                self._session_last_active[key] = now
                return self._active_sessions[key]

        # Create new session
        sid = generate_session_id()
        create_session(sid, source=platform, user_id=user_id,
                       model=self.config.get("model", "sonnet"))
        self._active_sessions[key] = sid
        self._session_last_active[key] = now
        log.info(f"New session: {sid} ({platform}:{chat_id})")
        return sid

    def _get_lock(self, session_key: str) -> asyncio.Lock:
        """Get or create a per-session lock to serialize agent calls."""
        if session_key not in self._locks:
            self._locks[session_key] = asyncio.Lock()
        return self._locks[session_key]

    # ── Message handler ──────────────────────────────────────────

    async def handle_message(self, platform: str, chat_id: str,
                              user_id: str, text: str) -> str:
        """Core message handler — called by platform adapters.

        Routes message to Claude Code and returns the response text.
        Serializes requests per session_key so concurrent messages
        from the same chat don't collide.
        """
        key = self._session_key(platform, chat_id)
        lock = self._get_lock(key)

        async with lock:
            session_id = self._get_or_create_session(platform, chat_id, user_id)

            # Persist user message
            add_message(session_id, "user", text)

            # Build context prefix
            context = (
                f"[Gateway context: platform={platform}, chat_id={chat_id}, "
                f"user_id={user_id}, session={session_id}]\n\n"
            )

            prompt = context + text
            model = self.config.get("model", "sonnet")

            # Run Claude Code in executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: invoke_claude(prompt, model=model)
            )

            response_text = result.get("text", "No response.")
            cost = result.get("cost", 0)

            # Persist assistant response
            add_message(session_id, "assistant", response_text)

            # Log cost
            if cost > 0:
                self._log_cost(platform, session_id, cost)

            return response_text

    # ── Cost tracking ────────────────────────────────────────────

    def _log_cost(self, platform: str, session_id: str, cost: float):
        """Append cost to logs/cost.log."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cost_file = LOG_DIR / "cost.log"
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts}\t{platform}\t{session_id}\t${cost:.4f}\n"
        with open(cost_file, "a") as f:
            f.write(line)

    # ── Session cleanup ──────────────────────────────────────────

    async def _session_cleanup_loop(self):
        """Periodically check for idle sessions and end them."""
        idle_minutes = self.config.get("session_idle_minutes", 120)
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(60)  # check every minute
                now = datetime.now(timezone.utc)
                expired_keys = []
                for key, last in self._session_last_active.items():
                    if (now - last) > timedelta(minutes=idle_minutes):
                        expired_keys.append(key)
                for key in expired_keys:
                    sid = self._active_sessions.pop(key, None)
                    self._session_last_active.pop(key, None)
                    self._locks.pop(key, None)
                    if sid:
                        end_session(sid)
                        log.info(f"Cleaned up idle session: {sid}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Session cleanup error: {e}")

    # ── Platform startup ─────────────────────────────────────────

    def _create_adapters(self):
        """Instantiate enabled platform adapters."""
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
                self.adapters.append(adapter)
                log.info(f"Platform {name}: created")
            except ImportError as e:
                log.warning(f"Platform {name}: skipped ({e})")
            except Exception as e:
                log.error(f"Platform {name}: failed to create ({e})")

    # ── Main lifecycle ───────────────────────────────────────────

    async def start(self):
        """Start the gateway: load config, start adapters, wait for shutdown."""
        # Load config
        self.config = load_config()
        log.info("Config loaded")

        # Create adapters
        self._create_adapters()

        if not self.adapters:
            log.error("No platform adapters enabled. Configure at least one in config.yaml or .env")
            log.error("Example: set TELEGRAM_BOT_TOKEN in ~/.agenticEvolve/.env")
            return

        # Start all adapters
        for adapter in self.adapters:
            try:
                await adapter.start()
            except Exception as e:
                log.error(f"Failed to start {adapter.name}: {e}")

        started = [a.name for a in self.adapters]
        log.info(f"Gateway running: {', '.join(started)}")

        # Write PID file
        PID_FILE.write_text(str(os.getpid()))

        # Start session cleanup
        self._session_cleanup_task = asyncio.create_task(self._session_cleanup_loop())

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    async def stop(self):
        """Graceful shutdown — stop all adapters, end active sessions."""
        log.info("Gateway shutting down...")

        # Cancel cleanup task
        if self._session_cleanup_task:
            self._session_cleanup_task.cancel()

        # Stop adapters
        for adapter in self.adapters:
            try:
                await adapter.stop()
            except Exception as e:
                log.error(f"Error stopping {adapter.name}: {e}")

        # End all active sessions
        for key, sid in self._active_sessions.items():
            end_session(sid)
        self._active_sessions.clear()

        # Remove PID file
        if PID_FILE.exists():
            PID_FILE.unlink()

        log.info("Gateway stopped")

    def request_shutdown(self):
        """Signal the gateway to shut down."""
        self._shutdown_event.set()


# ── Entry point ──────────────────────────────────────────────────

def setup_logging():
    """Configure logging to stderr + file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    stderr_handler.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(LOG_DIR / "gateway.log")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    root = logging.getLogger("agenticEvolve")
    root.setLevel(logging.DEBUG)
    root.addHandler(stderr_handler)
    root.addHandler(file_handler)

    # Quiet noisy libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)


async def start_gateway():
    """Async entry point — create runner, wire signals, start."""
    runner = GatewayRunner()

    loop = asyncio.get_running_loop()

    # Wire SIGINT/SIGTERM to graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, runner.request_shutdown)

    try:
        await runner.start()
    finally:
        await runner.stop()


def main():
    """Sync entry point."""
    setup_logging()
    log.info("Starting agenticEvolve gateway...")
    asyncio.run(start_gateway())


if __name__ == "__main__":
    main()
