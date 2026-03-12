"""Telegram platform adapter using python-telegram-bot."""
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .base import BasePlatformAdapter

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"
CRON_DIR = EXODIR / "cron"
CRON_JOBS_FILE = CRON_DIR / "jobs.json"

try:
    from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class TelegramAdapter(BasePlatformAdapter):
    name = "telegram"

    def __init__(self, config: dict, on_message):
        super().__init__(config, on_message)
        if not HAS_TELEGRAM:
            raise ImportError("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        self.token = config.get("token", "")
        self.allowed_users = set(str(u) for u in config.get("allowed_users", []))
        self.app = None
        self._gateway = None  # set by GatewayRunner after creation

    def _is_allowed(self, user_id: int) -> bool:
        if not self.allowed_users:
            return False
        return str(user_id) in self.allowed_users

    async def _deny(self, update: Update):
        user_id = update.message.from_user.id
        await update.message.reply_text(
            f"You are not verified to use this bot.\n\n"
            f"Your Telegram user ID: `{user_id}`\n\n"
            f"Please send this ID to the bot owner to request access.",
            parse_mode="Markdown"
        )

    # ── /start ───────────────────────────────────────────────────

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)
        await update.message.reply_text(
            "agenticEvolve connected.\n\n"
            "Send me any message and I'll process it with Claude Code.\n"
            "Use /help to see available commands."
        )

    # ── /help ────────────────────────────────────────────────────

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)
        await update.message.reply_text(
            "agenticEvolve commands\n\n"
            "Core\n"
            "/help — Show this help\n"
            "/status — System status\n"
            "/model [name] — View or switch model\n"
            "/cost — Today's cost\n"
            "/config — View runtime config\n"
            "/heartbeat — Check if bot is alive\n\n"
            "Sessions\n"
            "/newsession — Force new session\n"
            "/sessions — Recent sessions\n"
            "/search <query> — FTS5 search past sessions\n\n"
            "Memory & Identity\n"
            "/memory — Show bounded memory\n"
            "/soul — View agent personality\n\n"
            "Evolution\n"
            "/evolve — Scan signals + build skills now\n"
            "/evolve --dry-run — Preview what would be built\n"
            "/absorb <target> — Deep scan + implement improvements\n"
            "/absorb --dry-run <target> — Preview gaps only\n"
            "/learn <target> — Deep-dive + extract patterns\n"
            "/learnings — View past findings (or search)\n\n"
            "Skills\n"
            "/skills — List installed skills\n"
            "/queue — Skills pending approval\n"
            "/approve <name> — Install a queued skill\n"
            "/reject <name> — Remove a queued skill\n\n"
            "Scheduling\n"
            "/loop <interval> <prompt> — Recurring job\n"
            "/loops — List active loops\n"
            "/unloop <id> — Cancel a loop\n"
            "/pause <id> — Pause a loop\n"
            "/unpause <id> — Resume a loop\n"
            "/notify <delay> <msg> — One-shot reminder\n\n"
            "Maintenance\n"
            "/gc — Garbage collection + health check\n"
            "/gc dry — Preview without deleting\n\n"
            "Or just send any message to chat with Claude."
        )

    # ── /status ──────────────────────────────────────────────────

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..agent import get_today_cost
        from ..session_db import stats

        s = stats()
        today_cost = get_today_cost()
        mem_path = EXODIR / "memory" / "MEMORY.md"
        user_path = EXODIR / "memory" / "USER.md"
        mem_chars = len(mem_path.read_text()) if mem_path.exists() else 0
        user_chars = len(user_path.read_text()) if user_path.exists() else 0

        # Count skills
        skills_dir = Path.home() / ".claude" / "skills"
        skill_count = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.exists() else 0

        # Count cron jobs
        active_jobs = 0
        if CRON_JOBS_FILE.exists():
            try:
                jobs = json.loads(CRON_JOBS_FILE.read_text())
                active_jobs = sum(1 for j in jobs if not j.get("paused", False))
            except Exception:
                pass

        text = (
            f"*agenticEvolve status*\n\n"
            f"Gateway: running\n"
            f"Memory: {mem_chars}/2200 chars\n"
            f"User profile: {user_chars}/1375 chars\n"
            f"Sessions: {s['total_sessions']} total, {s['total_messages']} msgs\n"
            f"Skills: {skill_count} installed\n"
            f"Cron jobs: {active_jobs} active\n"
            f"DB: {s['db_size_mb']} MB\n"
            f"Cost today: ${today_cost:.2f}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    # ── /memory ──────────────────────────────────────────────────

    async def _handle_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        mem_path = EXODIR / "memory" / "MEMORY.md"
        user_path = EXODIR / "memory" / "USER.md"
        mem = mem_path.read_text().strip() if mem_path.exists() else "(empty)"
        user = user_path.read_text().strip() if user_path.exists() else "(empty)"

        text = (
            f"MEMORY.md ({len(mem)}/2200)\n\n{mem}\n\n"
            f"---\n\n"
            f"USER.md ({len(user)}/1375)\n\n{user}"
        )
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /sessions ────────────────────────────────────────────────

    async def _handle_sessions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..session_db import list_sessions
        rows = list_sessions(limit=10)
        if not rows:
            return await update.message.reply_text("No sessions yet.")

        lines = ["*Recent sessions*\n"]
        for r in rows:
            title = r.get("title") or "(untitled)"
            msgs = r.get("message_count", 0)
            src = r.get("source", "?")
            ts = r.get("started_at", "?")[:16]
            lines.append(f"`{ts}` {src} — {title} ({msgs} msgs)")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── /newsession ──────────────────────────────────────────────

    async def _handle_newsession(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        chat_id = str(update.message.chat_id)
        key = f"telegram:{chat_id}"
        if self._gateway:
            sid = self._gateway._active_sessions.pop(key, None)
            self._gateway._session_last_active.pop(key, None)
            self._gateway._session_msg_count.pop(key, None)
            self._gateway._locks.pop(key, None)
            if sid:
                from ..session_db import end_session
                end_session(sid)
        await update.message.reply_text("New session started. Send your next message.")

    # ── /cost ────────────────────────────────────────────────────

    async def _handle_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..agent import get_today_cost
        today_cost = get_today_cost()
        daily_cap = 5.0
        if self._gateway:
            daily_cap = self._gateway.config.get("daily_cost_cap", 5.0)
        await update.message.reply_text(
            f"*Cost today*: ${today_cost:.2f} / ${daily_cap:.2f}",
            parse_mode="Markdown"
        )

    # ── /model ───────────────────────────────────────────────────

    async def _handle_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        new_model = context.args[0] if context.args else ""
        if new_model:
            valid = {"sonnet", "opus", "haiku", "claude-sonnet-4-20250514",
                     "claude-opus-4-6", "claude-haiku-4-5-20251001"}
            if new_model not in valid:
                return await update.message.reply_text(
                    f"Unknown model: {new_model}\n\n"
                    f"Valid: sonnet, opus, haiku"
                )
            if self._gateway:
                self._gateway.config["model"] = new_model
                # Persist to config.yaml
                import yaml
                config_path = EXODIR / "config.yaml"
                try:
                    cfg = yaml.safe_load(config_path.read_text()) or {}
                    cfg["model"] = new_model
                    config_path.write_text(yaml.dump(cfg, default_flow_style=False))
                except Exception as e:
                    log.warning(f"Failed to persist model change: {e}")
            await update.message.reply_text(f"Model switched to: {new_model}")
        else:
            model = "sonnet"
            if self._gateway:
                model = self._gateway.config.get("model", "sonnet")
            await update.message.reply_text(f"Current model: {model}\n\nUsage: /model <sonnet|opus|haiku>")

    # ── /evolve ──────────────────────────────────────────────────

    async def _handle_evolve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run multi-stage evolve pipeline with live progress."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        dry_run = False
        if context.args and context.args[0].lower() in ("--dry-run", "dry-run", "dry", "preview"):
            dry_run = True

        chat_id = str(update.message.chat_id)
        if dry_run:
            await update.message.reply_text(
                "*Evolution dry run*\n\n"
                "Stages: COLLECT → ANALYZE (then stop)\n"
                "Will show what would be built without actually building.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "*Starting evolution pipeline...*\n\n"
                "Stages: COLLECT → ANALYZE → BUILD → REVIEW → REPORT\n"
                "Progress updates will appear below.",
                parse_mode="Markdown"
            )

        loop = asyncio.get_running_loop()

        # Bridge sync progress callback to async Telegram messages
        msg_buffer = []
        async def send_progress(text: str):
            msg_buffer.append(text)
            if len(msg_buffer) % 3 == 0:
                batch = "\n".join(msg_buffer[-3:])
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=batch, parse_mode="Markdown"
                    )
                except Exception:
                    pass

        def on_progress_sync(text: str):
            asyncio.run_coroutine_threadsafe(send_progress(text), loop)

        model = "sonnet"
        if self._gateway:
            model = self._gateway.config.get("model", "sonnet")

        try:
            from ..evolve import EvolveOrchestrator

            orchestrator = EvolveOrchestrator(model=model, on_progress=on_progress_sync)

            # Run pipeline in executor
            summary, cost = await loop.run_in_executor(
                None, lambda: orchestrator.run(dry_run=dry_run)
            )

            # Send remaining buffered progress
            remaining = len(msg_buffer) % 3
            if remaining > 0:
                batch = "\n".join(msg_buffer[-remaining:])
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=batch, parse_mode="Markdown"
                    )
                except Exception:
                    pass

            # Send final summary
            for i in range(0, len(summary), 4000):
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=summary[i:i+4000], parse_mode="Markdown"
                )

            if cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "evolve", cost)

        except Exception as e:
            log.error(f"Evolve error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Evolution failed: {e}")

    # ── /queue — list skills pending approval ────────────────────

    async def _handle_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..evolve import list_queue
        items = list_queue()

        if not items:
            return await update.message.reply_text("Skills queue is empty. Run /evolve to discover new tools.")

        lines = ["*Skills queue*\n"]
        for item in items:
            status = item["status"]
            name = item["name"]
            if status == "rejected":
                issues = item.get("review", {}).get("issues", [])
                lines.append(f"  `{name}` — rejected ({', '.join(issues[:2])})")
                lines.append(f"    /approve {name} force")
            else:
                lines.append(f"  `{name}` — pending review")
                lines.append(f"    /approve {name}")
            lines.append(f"    /reject {name}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── /approve — install a queued skill ────────────────────────

    async def _handle_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = context.args if context.args else []
        if not args:
            return await update.message.reply_text("Usage: `/approve <skill-name>` or `/approve <skill-name> force`", parse_mode="Markdown")

        name = args[0]
        force = len(args) > 1 and args[1] == "force"

        from ..evolve import approve_skill, approve_skill_force
        if force:
            ok, msg = approve_skill_force(name)
        else:
            ok, msg = approve_skill(name)

        await update.message.reply_text(msg, parse_mode="Markdown")

    # ── /reject — remove a queued skill ──────────────────────────

    async def _handle_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = context.args if context.args else []
        if not args:
            return await update.message.reply_text("Usage: `/reject <skill-name> [reason]`", parse_mode="Markdown")

        name = args[0]
        reason = " ".join(args[1:]) if len(args) > 1 else ""

        from ..evolve import reject_skill
        ok, msg = reject_skill(name, reason)
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ── /loop — create recurring cron job ────────────────────────

    async def _handle_loop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = " ".join(context.args) if context.args else ""
        if not args:
            await update.message.reply_text(
                "*Usage:* `/loop <interval> <prompt>`\n\n"
                "*Examples:*\n"
                "`/loop 2h scan HN for AI tools`\n"
                "`/loop 30m check GitHub trending`\n"
                "`/loop 1d summarize today's tech news`\n\n"
                "*Intervals:* `s` sec, `m` min, `h` hours, `d` days (min 60s)",
                parse_mode="Markdown"
            )
            return

        parts = args.split(None, 1)
        if len(parts) < 2:
            return await update.message.reply_text("Need interval and prompt. Example: `/loop 2h scan HN`", parse_mode="Markdown")

        interval_str, prompt = parts[0], parts[1].strip()
        match = re.fullmatch(r"(\d+)(s|m|h|d)", interval_str.lower())
        if not match:
            return await update.message.reply_text(f"Invalid interval `{interval_str}`. Use `30s`, `5m`, `2h`, `1d`.", parse_mode="Markdown")

        value, unit = int(match.group(1)), match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        interval_seconds = value * multipliers[unit]
        if interval_seconds < 60:
            return await update.message.reply_text("Minimum interval is 60 seconds.")

        CRON_DIR.mkdir(parents=True, exist_ok=True)
        jobs = []
        if CRON_JOBS_FILE.exists():
            try:
                jobs = json.loads(CRON_JOBS_FILE.read_text())
            except Exception:
                jobs = []

        job_id = uuid.uuid4().hex[:8]
        chat_id = str(update.message.chat_id)
        now = datetime.now(timezone.utc)

        job = {
            "id": job_id,
            "prompt": prompt,
            "schedule_type": "interval",
            "interval_seconds": interval_seconds,
            "deliver_to": "telegram",
            "deliver_chat_id": chat_id,
            "created_at": now.isoformat(),
            "next_run_at": (now + timedelta(seconds=interval_seconds)).isoformat(),
            "run_count": 0,
            "paused": False,
            "last_run_at": None,
        }
        jobs.append(job)
        CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))

        unit_names = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
        await update.message.reply_text(
            f"Loop created: `{job_id}`\n"
            f"Every {value} {unit_names[unit]}: {prompt}\n"
            f"Next run: {job['next_run_at'][:19]}",
            parse_mode="Markdown"
        )

    # ── /loops — list active cron jobs ───────────────────────────

    async def _handle_loops(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        if not CRON_JOBS_FILE.exists():
            return await update.message.reply_text("No loops configured.")

        try:
            jobs = json.loads(CRON_JOBS_FILE.read_text())
        except Exception:
            return await update.message.reply_text("Error reading jobs.json.")

        if not jobs:
            return await update.message.reply_text("No loops configured.")

        lines = ["*Active loops*\n"]
        for j in jobs:
            status = "paused" if j.get("paused") else "active"
            prompt_preview = j.get("prompt", "")[:60]
            runs = j.get("run_count", 0)
            interval = j.get("interval_seconds", 0)
            if interval >= 86400:
                freq = f"{interval // 86400}d"
            elif interval >= 3600:
                freq = f"{interval // 3600}h"
            elif interval >= 60:
                freq = f"{interval // 60}m"
            else:
                freq = f"{interval}s"
            lines.append(f"`{j['id']}` [{status}] every {freq} ({runs} runs)\n  {prompt_preview}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── /unloop — cancel a cron job ──────────────────────────────

    async def _handle_unloop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        job_id = context.args[0] if context.args else ""
        if not job_id:
            return await update.message.reply_text("Usage: `/unloop <job_id>`", parse_mode="Markdown")

        if not CRON_JOBS_FILE.exists():
            return await update.message.reply_text("No loops configured.")

        try:
            jobs = json.loads(CRON_JOBS_FILE.read_text())
        except Exception:
            return await update.message.reply_text("Error reading jobs.json.")

        new_jobs = [j for j in jobs if j.get("id") != job_id]
        if len(new_jobs) == len(jobs):
            return await update.message.reply_text(f"Loop `{job_id}` not found.", parse_mode="Markdown")

        CRON_JOBS_FILE.write_text(json.dumps(new_jobs, indent=2))
        await update.message.reply_text(f"Loop `{job_id}` removed.", parse_mode="Markdown")

    # ── /heartbeat — check if bot is alive ─────────────────────

    async def _handle_heartbeat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        import time
        uptime = "unknown"
        if self._gateway and hasattr(self._gateway, '_start_time'):
            elapsed = time.time() - self._gateway._start_time
            hours, rem = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(rem, 60)
            uptime = f"{hours}h {minutes}m {seconds}s"

        pid = os.getpid()
        from ..agent import get_today_cost
        cost = get_today_cost()

        await update.message.reply_text(
            f"*Heartbeat*\n\n"
            f"Status: alive\n"
            f"PID: {pid}\n"
            f"Uptime: {uptime}\n"
            f"Cost today: ${cost:.2f}",
            parse_mode="Markdown"
        )

    # ── /notify — send a reminder to yourself later ──────────────

    async def _handle_notify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Schedule a one-shot reminder. Usage: /notify <delay> <message>"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = " ".join(context.args) if context.args else ""
        if not args:
            await update.message.reply_text(
                "Usage: /notify <delay> <message>\n\n"
                "Examples:\n"
                "/notify 60s check if build finished\n"
                "/notify 30m check deployment status\n"
                "/notify 2h review PR feedback\n"
                "/notify 1d renew API key"
            )
            return

        parts = args.split(None, 1)
        if len(parts) < 2:
            return await update.message.reply_text("Need delay and message. Example: `/notify 30m check the build`", parse_mode="Markdown")

        delay_str, message = parts[0], parts[1].strip()
        match = re.fullmatch(r"(\d+)(s|m|h|d)", delay_str.lower())
        if not match:
            return await update.message.reply_text(f"Invalid delay `{delay_str}`. Use `60s`, `30m`, `2h`, `1d`.", parse_mode="Markdown")

        value, unit = int(match.group(1)), match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        delay_seconds = value * multipliers[unit]

        CRON_DIR.mkdir(parents=True, exist_ok=True)
        jobs = []
        if CRON_JOBS_FILE.exists():
            try:
                jobs = json.loads(CRON_JOBS_FILE.read_text())
            except Exception:
                jobs = []

        job_id = uuid.uuid4().hex[:8]
        chat_id = str(update.message.chat_id)
        now = datetime.now(timezone.utc)
        run_at = now + timedelta(seconds=delay_seconds)

        job = {
            "id": job_id,
            "prompt": f"Send this reminder to the user: {message}",
            "schedule_type": "once",
            "interval_seconds": 0,
            "deliver_to": "telegram",
            "deliver_chat_id": chat_id,
            "created_at": now.isoformat(),
            "next_run_at": run_at.isoformat(),
            "run_count": 0,
            "paused": False,
            "last_run_at": None,
        }
        jobs.append(job)
        CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))

        unit_names = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
        await update.message.reply_text(
            f"Reminder set: {job_id}\n"
            f"In {value} {unit_names[unit]}: {message}\n"
            f"Will fire at: {run_at.strftime('%H:%M UTC')}"
        )

    # ── /learn — deep-dive a repo or tech ──────────────────────

    async def _handle_learn(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deep-dive a repo, library, or tech. Analyze how we benefit and optionally build a skill."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        target = " ".join(context.args) if context.args else ""
        if not target:
            await update.message.reply_text(
                "*Usage:* `/learn <repo-url or tech name>`\n\n"
                "*Examples:*\n"
                "`/learn https://github.com/vercel/ai`\n"
                "`/learn anthropic tool-use patterns`\n"
                "`/learn htmx`\n"
                "`/learn https://github.com/nicepkg/aide`",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(
            f"Learning about `{target}`...\n\nI'll research it, analyze how it benefits us, and suggest if we should build a skill for it.",
            parse_mode="Markdown"
        )

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        loop = asyncio.get_running_loop()

        # Build progress bridge
        msg_buffer = []
        async def send_progress(text: str):
            msg_buffer.append(text)
            if len(msg_buffer) % 3 == 0:
                batch = "\n".join(msg_buffer[-3:])
                try:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=batch, parse_mode="Markdown")
                except Exception:
                    pass

        def on_progress_sync(text: str):
            asyncio.run_coroutine_threadsafe(send_progress(text), loop)

        is_url = target.startswith("http://") or target.startswith("https://")
        is_github = "github.com" in target

        # Common context about our system for the learn agent
        system_context = (
            f"You are the LEARN agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
            f"Our system: Python asyncio gateway → Claude Code (claude -p) → Telegram. "
            f"Bounded memory (MEMORY.md/USER.md), SQLite+FTS5 sessions, agent-managed cron, "
            f"skills in ~/.claude/skills/, safety-gated skill queue.\n\n"
            f"Vincent builds AI agents, onchain infrastructure, and developer tools. "
            f"Stack: TypeScript/React frontends, Python for infra/agents.\n\n"
        )

        # The core of /learn: extract patterns, evaluate operational benefit
        analysis_instructions = (
            f"EXTRACT PATTERNS:\n"
            f"- What design patterns, architectural decisions, or techniques does this use?\n"
            f"- What can we steal and apply to our own system — even if we don't use this tool directly?\n"
            f"- Are there code patterns that would improve our gateway, memory system, cron, or agent invocation?\n\n"
            f"EVALUATE OPERATIONAL BENEFIT:\n"
            f"- Does this solve a real problem we have right now? Be specific.\n"
            f"- Would adopting this speed up our development workflow or make our agent system more capable?\n"
            f"- What's the cost/effort vs benefit? Is it worth the integration work?\n"
            f"- Verdict: ADOPT (use it) / STEAL (take patterns, skip the dep) / SKIP (not useful for us)\n\n"
            f"IF VERDICT IS ADOPT OR STEAL:\n"
            f"- Create a skill in ~/.agenticEvolve/skills-queue/<name>/SKILL.md with concrete instructions\n"
            f"- Include a Source: <url> line at the bottom of the SKILL.md\n"
            f"- The skill goes to queue for review, NOT auto-installed\n\n"
            f"MEMORY UPDATE:\n"
            f"- Add a concise entry about what we learned to ~/.agenticEvolve/memory/MEMORY.md\n"
            f"- Focus on the extractable pattern, not a description of the tool\n"
            f"- Use § as separator, respect the 2200 char limit\n\n"
            f"STRUCTURED OUTPUT (REQUIRED):\n"
            f"At the END of your response, include this JSON block so we can store the learning:\n"
            f"```json\n"
            f'{{"verdict": "ADOPT|STEAL|SKIP", '
            f'"patterns": "key patterns extracted (1-3 sentences)", '
            f'"operational_benefit": "how this helps our system (1-2 sentences)", '
            f'"skill_created": "skill-name or empty string"}}\n'
            f"```\n\n"
        )

        if is_github:
            learn_prompt = (
                system_context +
                f"Deep-dive this GitHub repo: {target}\n\n"
                f"1. Clone the repo to a temp directory (or use WebFetch/gh to read it)\n"
                f"2. Read the README, key source files, and architecture\n"
                f"3. Understand how it works — focus on the interesting engineering, not surface features\n\n"
                + analysis_instructions +
                f"Return: patterns extracted, operational verdict, and any skill/memory updates made."
            )
        elif is_url:
            learn_prompt = (
                system_context +
                f"Research this URL: {target}\n\n"
                f"1. Fetch the page content using WebFetch\n"
                f"2. Find the source repo if it exists\n"
                f"3. Understand the core idea and how it's implemented\n\n"
                + analysis_instructions +
                f"Return: patterns extracted, operational verdict, and any skill/memory updates made."
            )
        else:
            learn_prompt = (
                system_context +
                f"Research this technology/concept: {target}\n\n"
                f"1. Search the web for '{target}' — find the repo, docs, key resources\n"
                f"2. Understand how it works and what problem it solves\n"
                f"3. Look at the source code if available — the patterns matter more than the docs\n\n"
                + analysis_instructions +
                f"Return: patterns extracted, operational verdict, and any skill/memory updates made."
            )

        model = "sonnet"
        if self._gateway:
            model = self._gateway.config.get("model", "sonnet")

        try:
            from ..agent import invoke_claude_streaming

            result = await loop.run_in_executor(
                None,
                lambda: invoke_claude_streaming(
                    learn_prompt,
                    on_progress=on_progress_sync,
                    model=model,
                    session_context=f"[Learn: {target[:50]}]"
                )
            )

            # Flush remaining progress
            remaining = len(msg_buffer) % 3
            if remaining > 0:
                batch = "\n".join(msg_buffer[-remaining:])
                try:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=batch, parse_mode="Markdown")
                except Exception:
                    pass

            response = result.get("text", "No output.")
            cost = result.get("cost", 0)

            header = f"*Learn: {target}* (${cost:.2f})\n\n"
            full = header + response
            for i in range(0, len(full), 4000):
                await self.app.bot.send_message(chat_id=int(chat_id), text=full[i:i+4000], parse_mode="Markdown")

            if cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "learn", cost)

            # Store learning in DB
            try:
                from ..session_db import add_learning
                # Parse structured JSON from response
                learning_data = {"verdict": "UNKNOWN", "patterns": "", "operational_benefit": "", "skill_created": ""}
                json_start = response.rfind('```json')
                json_end = response.rfind('```', json_start + 7) if json_start >= 0 else -1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start + 7:json_end].strip()
                    try:
                        learning_data = json.loads(json_str)
                    except (json.JSONDecodeError, ValueError):
                        pass

                target_type = "github" if is_github else ("url" if is_url else "topic")
                add_learning(
                    target=target,
                    target_type=target_type,
                    verdict=learning_data.get("verdict", "UNKNOWN"),
                    patterns=learning_data.get("patterns", ""),
                    operational_benefit=learning_data.get("operational_benefit", ""),
                    skill_created=learning_data.get("skill_created", ""),
                    full_report=response[:8000],
                    cost=cost,
                )
                log.info(f"[learn] Stored learning: {target} -> {learning_data.get('verdict', '?')}")
            except Exception as e:
                log.warning(f"[learn] Failed to store learning: {e}")

        except Exception as e:
            log.error(f"Learn error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Learn failed: {e}")

    # ── /absorb — deep scan + implement improvements ───────────

    async def _handle_absorb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deep scan a target, analyze gaps in our system, and implement improvements."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        # Parse --dry-run flag from args
        dry_run = False
        raw_args = list(context.args) if context.args else []
        for flag in ("--dry-run", "dry-run", "dry", "preview"):
            if flag in raw_args:
                dry_run = True
                raw_args.remove(flag)
                break

        target = " ".join(raw_args)
        if not target:
            await update.message.reply_text(
                "*Usage:* `/absorb <repo-url or tech/architecture>`\n\n"
                "*Options:*\n"
                "`/absorb --dry-run <target>` — scan + gap analysis only\n\n"
                "*Examples:*\n"
                "`/absorb https://github.com/NousResearch/hermes-agent`\n"
                "`/absorb persistent memory protocol for ai agents`\n"
                "`/absorb --dry-run https://github.com/langchain-ai/langgraph`\n"
                "`/absorb bounded context window management`\n\n"
                "This will deep scan the target, compare against our system, "
                "identify gaps, and *actually implement improvements*.\n"
                "Use `--dry-run` to preview gaps without implementing.",
                parse_mode="Markdown"
            )
            return

        is_url = target.startswith("http://") or target.startswith("https://")
        is_github = "github.com" in target
        target_type = "github" if is_github else ("url" if is_url else "topic")

        if dry_run:
            await update.message.reply_text(
                f"*Absorb dry run:* `{target}`\n\n"
                f"Stages: SCAN → GAP (then stop)\n"
                f"Will show gaps without implementing changes.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"*Absorbing:* `{target}`\n\n"
                f"Stages: SCAN → GAP → PLAN → IMPLEMENT → REPORT\n\n"
                f"This will analyze the target, find what our system is missing, "
                f"and implement improvements. Progress below.",
                parse_mode="Markdown"
            )

        chat_id = str(update.message.chat_id)
        loop = asyncio.get_running_loop()

        # Progress bridge
        msg_buffer = []
        async def send_progress(text: str):
            msg_buffer.append(text)
            if len(msg_buffer) % 3 == 0:
                batch = "\n".join(msg_buffer[-3:])
                try:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=batch, parse_mode="Markdown")
                except Exception:
                    pass

        def on_progress_sync(text: str):
            asyncio.run_coroutine_threadsafe(send_progress(text), loop)

        model = "sonnet"
        if self._gateway:
            model = self._gateway.config.get("model", "sonnet")

        try:
            from ..absorb import AbsorbOrchestrator

            orchestrator = AbsorbOrchestrator(
                target=target,
                target_type=target_type,
                model=model,
                on_progress=on_progress_sync,
            )

            summary, cost = await loop.run_in_executor(
                None, lambda: orchestrator.run(dry_run=dry_run)
            )

            # Flush remaining progress
            remaining = len(msg_buffer) % 3
            if remaining > 0:
                batch = "\n".join(msg_buffer[-remaining:])
                try:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=batch, parse_mode="Markdown")
                except Exception:
                    pass

            # Send final summary
            for i in range(0, len(summary), 4000):
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=summary[i:i+4000], parse_mode="Markdown"
                )

            if cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "absorb", cost)

            # Store in learnings DB
            try:
                from ..session_db import add_learning
                add_learning(
                    target=target,
                    target_type=target_type,
                    verdict="ABSORBED",
                    patterns=f"Absorbed via 5-stage pipeline. See full report.",
                    operational_benefit=f"System improvements implemented. Cost: ${cost:.2f}",
                    skill_created="",
                    full_report=summary[:8000],
                    cost=cost,
                )
            except Exception as e:
                log.warning(f"[absorb] Failed to store learning: {e}")

        except Exception as e:
            log.error(f"Absorb error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Absorb failed: {e}")

    # ── /learnings — view past learnings ────────────────────────

    async def _handle_learnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List past learnings or search them."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        query = " ".join(context.args) if context.args else ""

        from ..session_db import list_learnings, search_learnings

        if query:
            items = search_learnings(query, limit=10)
        else:
            items = list_learnings(limit=10)

        if not items:
            msg = "No learnings stored yet. Use `/learn <topic>` to start." if not query else f"No learnings matching `{query}`."
            return await update.message.reply_text(msg, parse_mode="Markdown")

        lines = [f"*Learnings{' matching: ' + query if query else ''}*\n"]
        for item in items:
            verdict = item.get("verdict", "?")
            target = item.get("target", "?")
            patterns = item.get("patterns", "")
            created = item.get("created_at", "")[:10]
            skill = item.get("skill_created", "")

            lines.append(f"*{target}* [{verdict}] ({created})")
            if patterns:
                lines.append(f"  {patterns[:200]}")
            if skill:
                lines.append(f"  Skill: `{skill}`")
            lines.append("")

        text = "\n".join(lines)
        for i in range(0, len(text), 4000):
            await self.app.bot.send_message(
                chat_id=update.message.chat_id, text=text[i:i+4000], parse_mode="Markdown"
            )

    # ── /gc — garbage collection ────────────────────────────────

    async def _handle_gc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run garbage collection — clean stale sessions, orphan skills, check memory health."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        dry_run = False
        if context.args and context.args[0].lower() in ("dry", "dry-run", "preview"):
            dry_run = True

        mode = "preview" if dry_run else "cleanup"
        await update.message.reply_text(f"Running GC ({mode})...", parse_mode="Markdown")

        chat_id = str(update.message.chat_id)
        loop = asyncio.get_running_loop()

        try:
            from ..gc import run_gc, format_gc_report

            report = await loop.run_in_executor(None, lambda: run_gc(dry_run=dry_run))
            text = format_gc_report(report)

            for i in range(0, len(text), 4000):
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=text[i:i+4000], parse_mode="Markdown"
                )
        except Exception as e:
            log.error(f"GC error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"GC failed: {e}")

    # ── Regular messages ─────────────────────────────────────────

    # ── /search — FTS5 search across past sessions ─────────────

    async def _handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search past sessions using FTS5. Usage: /search <query>"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        query = " ".join(context.args) if context.args else ""
        if not query:
            await update.message.reply_text(
                "Usage: /search <query>\n\n"
                "Examples:\n"
                "/search telegram rate limit\n"
                "/search cost cap\n"
                "/search absorb pipeline"
            )
            return

        from ..session_db import search_sessions
        results = search_sessions(query, limit=5)

        if not results:
            await update.message.reply_text(f"No results for: {query}")
            return

        lines = [f"Search results for: {query}\n"]
        for r in results:
            title = r.get("title", "Untitled") or "Untitled"
            sid = r["session_id"][:8]
            started = r.get("started_at", "")[:10]
            match_count = len(r.get("matches", []))
            lines.append(f"\n[{sid}] {title} ({started})")
            for m in r.get("matches", [])[:2]:
                snippet = m["content"][:200].replace("\n", " ")
                lines.append(f"  {m['role']}: {snippet}")
            if match_count > 2:
                lines.append(f"  ... +{match_count - 2} more matches")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /skills — list installed skills ──────────────────────────

    async def _handle_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all installed Claude Code skills."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        skills_dir = Path.home() / ".claude" / "skills"
        if not skills_dir.exists():
            return await update.message.reply_text("No skills directory found.")

        skills = sorted(skills_dir.glob("*/SKILL.md"))
        if not skills:
            return await update.message.reply_text("No skills installed.")

        lines = [f"Installed skills ({len(skills)})\n"]
        for skill_path in skills:
            name = skill_path.parent.name
            # Read first line of description from frontmatter
            desc = ""
            try:
                content = skill_path.read_text()
                for line in content.splitlines():
                    if line.startswith("description:"):
                        desc = line[12:].strip()[:100]
                        break
            except Exception:
                pass

            # Check if disable-model-invocation
            explicit = ""
            try:
                if "disable-model-invocation: true" in skill_path.read_text():
                    explicit = " [explicit]"
            except Exception:
                pass

            lines.append(f"  {name}{explicit}")
            if desc:
                lines.append(f"    {desc}")

        # Queue count
        queue_dir = EXODIR / "skills-queue"
        queued = len(list(queue_dir.glob("*/SKILL.md"))) if queue_dir.exists() else 0
        if queued:
            lines.append(f"\nQueued: {queued} pending approval")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /soul — view SOUL.md ─────────────────────────────────────

    async def _handle_soul(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display the agent's SOUL.md personality definition."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        soul_path = EXODIR / "SOUL.md"
        if not soul_path.exists():
            return await update.message.reply_text("SOUL.md not found.")

        soul = soul_path.read_text().strip()
        text = f"SOUL.md ({len(soul)} chars)\n\n{soul}"
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /config — view runtime configuration ─────────────────────

    async def _handle_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current runtime configuration (no secrets)."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        cfg = self._gateway.config if self._gateway else {}

        model = cfg.get("model", "sonnet")
        daily_cap = cfg.get("daily_cost_cap", 5.0)
        weekly_cap = cfg.get("weekly_cost_cap", 25.0)
        session_idle = cfg.get("session_idle_minutes", 120)
        cron_enabled = cfg.get("cron", {}).get("enabled", True)

        platforms = []
        for pname, pcfg in cfg.get("platforms", {}).items():
            status = "enabled" if pcfg.get("enabled", False) else "disabled"
            users = len(pcfg.get("allowed_users", []))
            platforms.append(f"  {pname}: {status} ({users} users)")

        text = (
            f"Configuration\n\n"
            f"Model: {model}\n"
            f"Daily cap: ${daily_cap:.2f}\n"
            f"Weekly cap: ${weekly_cap:.2f}\n"
            f"Session idle timeout: {session_idle}m\n"
            f"Cron scheduler: {'on' if cron_enabled else 'off'}\n\n"
            f"Platforms:\n" + "\n".join(platforms)
        )
        await update.message.reply_text(text)

    # ── /pause, /unpause — toggle cron job ───────────────────────

    async def _handle_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pause a cron job. Usage: /pause <id>"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)
        await self._toggle_job(update, context, paused=True)

    async def _handle_unpause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unpause a cron job. Usage: /unpause <id>"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)
        await self._toggle_job(update, context, paused=False)

    async def _toggle_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE, paused: bool):
        """Shared logic for pause/unpause."""
        job_id = context.args[0] if context.args else ""
        if not job_id:
            action = "pause" if paused else "unpause"
            return await update.message.reply_text(f"Usage: /{action} <job_id>\n\nUse /loops to see job IDs.")

        if not CRON_JOBS_FILE.exists():
            return await update.message.reply_text("No jobs configured.")

        try:
            jobs = json.loads(CRON_JOBS_FILE.read_text())
        except Exception:
            return await update.message.reply_text("Failed to read jobs.json.")

        found = False
        for job in jobs:
            if job.get("id") == job_id:
                job["paused"] = paused
                found = True
                break

        if not found:
            return await update.message.reply_text(f"Job not found: {job_id}")

        CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))
        action = "Paused" if paused else "Unpaused"
        await update.message.reply_text(f"{action} job: {job_id}")

    # ── /model — view or switch model ────────────────────────────
    # (overrides the existing read-only /model handler above)

    # ── URL/link detection helper ───────────────────────────────

    _URL_RE = re.compile(
        r'https?://(?:github\.com|gitlab\.com|bitbucket\.org|npmjs\.com|pypi\.org|'
        r'huggingface\.co|arxiv\.org|medium\.com|dev\.to|blog\.|docs\.|'
        r'[\w.-]+\.(?:com|org|io|dev|ai|sh|co))/\S+',
        re.IGNORECASE
    )

    def _extract_urls(self, text: str) -> list[str]:
        """Extract meaningful URLs from text (not just any link)."""
        return self._URL_RE.findall(text)

    async def _offer_absorb_learn(self, update: Update, target: str, target_type: str = "link"):
        """Show inline keyboard asking user if they want to absorb/learn a target."""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Absorb", callback_data=f"absorb:{target[:200]}"),
                InlineKeyboardButton("Learn", callback_data=f"learn:{target[:200]}"),
            ],
            [
                InlineKeyboardButton("Just chat", callback_data="chat:proceed"),
            ]
        ])
        await update.message.reply_text(
            f"I noticed a {target_type}. Want me to absorb it into our system or learn from it?\n\n"
            f"{target[:200]}",
            reply_markup=keyboard
        )

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses for absorb/learn prompts."""
        query = update.callback_query
        if not query or not query.data:
            return
        await query.answer()

        user_id = query.from_user.id
        if not self._is_allowed(user_id):
            return

        chat_id = str(query.message.chat_id)
        data = query.data

        if data.startswith("absorb:"):
            target = data[7:]
            await query.edit_message_text(f"Absorbing: {target[:100]}...")
            # Trigger absorb pipeline
            context.args = [target]
            fake_update = update
            fake_update._effective_message = query.message
            await self._handle_absorb(update, context)

        elif data.startswith("learn:"):
            target = data[6:]
            await query.edit_message_text(f"Learning from: {target[:100]}...")
            # Trigger learn pipeline
            context.args = [target]
            fake_update = update
            fake_update._effective_message = query.message
            await self._handle_learn(update, context)

        elif data == "chat:proceed":
            # User chose to just chat — remove the keyboard and let it be
            await query.edit_message_text("Got it, continuing as normal chat.")

    # ── Photo/image handler ──────────────────────────────────────

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photos sent to the bot."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        caption = update.message.caption or ""

        # If photo has a URL in the caption, offer absorb/learn
        urls = self._extract_urls(caption) if caption else []
        if urls:
            await self._offer_absorb_learn(update, urls[0], "link in image caption")
            return

        # Otherwise just acknowledge — we can't process images directly via claude -p
        await update.message.reply_text(
            "I received your image but I can't process images directly through the gateway yet.\n\n"
            "If you have a URL to share, send it as text and I'll offer to absorb or learn from it."
        )

    # ── Regular text messages ────────────────────────────────────

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        user_id = update.message.from_user.id
        if not self._is_allowed(user_id):
            return await self._deny(update)

        chat_id = str(update.message.chat_id)
        text = update.message.text

        # Detect URLs — offer absorb/learn if the message is primarily a link
        urls = self._extract_urls(text)
        if urls:
            # If the message is mostly just a URL (link share), offer absorb/learn
            non_url_text = text
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                # Message is primarily a link share
                await self._offer_absorb_learn(update, urls[0], "link")
                return

        # Keep typing indicator alive while Claude processes
        typing_active = True
        async def keep_typing():
            while typing_active:
                try:
                    await update.message.chat.send_action("typing")
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(keep_typing())

        try:
            response = await self.on_message("telegram", chat_id, str(user_id), text)
            if response:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
        except Exception as e:
            log.error(f"Telegram handler error: {e}")
            await update.message.reply_text(f"Error: {e}")
        finally:
            typing_active = False
            typing_task.cancel()

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self):
        if not self.token:
            log.warning("Telegram token not set, skipping")
            return
        self.app = Application.builder().token(self.token).build()

        # Command handlers
        commands = {
            "start": self._handle_start,
            "help": self._handle_help,
            "status": self._handle_status,
            "memory": self._handle_memory,
            "sessions": self._handle_sessions,
            "newsession": self._handle_newsession,
            "cost": self._handle_cost,
            "model": self._handle_model,
            "evolve": self._handle_evolve,
            "loop": self._handle_loop,
            "loops": self._handle_loops,
            "unloop": self._handle_unloop,
            "heartbeat": self._handle_heartbeat,
            "notify": self._handle_notify,
            "queue": self._handle_queue,
            "approve": self._handle_approve,
            "reject": self._handle_reject,
            "learn": self._handle_learn,
            "gc": self._handle_gc,
            "absorb": self._handle_absorb,
            "learnings": self._handle_learnings,
            "search": self._handle_search,
            "skills": self._handle_skills,
            "soul": self._handle_soul,
            "config": self._handle_config,
            "pause": self._handle_pause,
            "unpause": self._handle_unpause,
        }
        for cmd, handler in commands.items():
            self.app.add_handler(CommandHandler(cmd, handler))

        # Regular text messages
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        # Photo handler
        self.app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))

        # Inline keyboard callback handler (absorb/learn/chat buttons)
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

        # Set bot menu commands
        try:
            await self.app.bot.set_my_commands([
                BotCommand("help", "Show available commands"),
                BotCommand("evolve", "Scan signals + build skills"),
                BotCommand("absorb", "Deep scan + implement improvements"),
                BotCommand("learn", "Deep-dive a repo or tech"),
                BotCommand("status", "System status"),
                BotCommand("heartbeat", "Check if bot is alive"),
                BotCommand("memory", "Show bounded memory"),
                BotCommand("sessions", "Recent sessions"),
                BotCommand("newsession", "Start new session"),
                BotCommand("cost", "Today's cost"),
                BotCommand("model", "Current model"),
                BotCommand("loop", "Create recurring job"),
                BotCommand("loops", "List active loops"),
                BotCommand("unloop", "Cancel a loop"),
                BotCommand("notify", "Set a reminder"),
                BotCommand("queue", "Skills pending approval"),
                BotCommand("approve", "Install a queued skill"),
                BotCommand("reject", "Remove a queued skill"),
                BotCommand("learnings", "View past /learn findings"),
                BotCommand("gc", "Garbage collection + health check"),
                BotCommand("search", "Search past sessions (FTS5)"),
                BotCommand("skills", "List installed skills"),
                BotCommand("soul", "View agent personality"),
                BotCommand("config", "View runtime config"),
                BotCommand("pause", "Pause a cron job"),
                BotCommand("unpause", "Resume a paused cron job"),
            ])
        except Exception as e:
            log.warning(f"Failed to set bot commands: {e}")

        log.info("Telegram adapter started")

    async def stop(self):
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            log.info("Telegram adapter stopped")

    async def send(self, chat_id: str, text: str):
        if self.app and self.app.bot:
            for i in range(0, len(text), 4000):
                await self.app.bot.send_message(chat_id=int(chat_id), text=text[i:i+4000])
