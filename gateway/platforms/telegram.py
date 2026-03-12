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
    from telegram import Update, BotCommand
    from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
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
            "*agenticEvolve commands*\n\n"
            "*Core*\n"
            "/help — Show this help\n"
            "/status — System status\n"
            "/model — Current model\n"
            "/cost — Today's cost\n"
            "/heartbeat — Check if bot is alive\n\n"
            "*Sessions*\n"
            "/newsession — Force new session\n"
            "/sessions — Recent sessions\n\n"
            "*Memory*\n"
            "/memory — Show bounded memory\n\n"
            "*Evolution*\n"
            "/evolve — Scan signals + build skills now\n"
            "/learn `<repo-url or tech>` — Deep-dive a repo or tech\n\n"
            "*Skills Queue*\n"
            "/queue — Skills pending approval\n"
            "/approve `<name>` — Install a queued skill\n"
            "/reject `<name>` — Remove a queued skill\n\n"
            "*Scheduling*\n"
            "/loop `<interval>` `<prompt>` — Recurring job\n"
            "/loops — List active loops\n"
            "/unloop `<id>` — Cancel a loop\n"
            "/notify `<delay>` `<msg>` — One-shot reminder\n\n"
            "*Maintenance*\n"
            "/gc — Garbage collection + health check\n"
            "/gc `dry` — Preview without deleting\n\n"
            "Or just send any message to chat with Claude.",
            parse_mode="Markdown"
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
            f"*MEMORY.md* ({len(mem)}/2200)\n\n{mem}\n\n"
            f"---\n\n"
            f"*USER.md* ({len(user)}/1375)\n\n{user}"
        )
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text, parse_mode="Markdown")

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
        model = "sonnet"
        if self._gateway:
            model = self._gateway.config.get("model", "sonnet")
        await update.message.reply_text(f"Current model: `{model}`", parse_mode="Markdown")

    # ── /evolve ──────────────────────────────────────────────────

    async def _handle_evolve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run multi-stage evolve pipeline with live progress."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        chat_id = str(update.message.chat_id)
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

            # Run full pipeline in executor
            summary, cost = await loop.run_in_executor(None, orchestrator.run)

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
                "*Usage:* `/notify <delay> <message>`\n\n"
                "*Examples:*\n"
                "`/notify 30m check deployment status`\n"
                "`/notify 2h review PR feedback`\n"
                "`/notify 1d renew API key`",
                parse_mode="Markdown"
            )
            return

        parts = args.split(None, 1)
        if len(parts) < 2:
            return await update.message.reply_text("Need delay and message. Example: `/notify 30m check the build`", parse_mode="Markdown")

        delay_str, message = parts[0], parts[1].strip()
        match = re.fullmatch(r"(\d+)(m|h|d)", delay_str.lower())
        if not match:
            return await update.message.reply_text(f"Invalid delay `{delay_str}`. Use `30m`, `2h`, `1d`.", parse_mode="Markdown")

        value, unit = int(match.group(1)), match.group(2)
        multipliers = {"m": 60, "h": 3600, "d": 86400}
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

        unit_names = {"m": "minutes", "h": "hours", "d": "days"}
        await update.message.reply_text(
            f"Reminder set: `{job_id}`\n"
            f"In {value} {unit_names[unit]}: {message}\n"
            f"Will fire at: {run_at.strftime('%H:%M UTC')}",
            parse_mode="Markdown"
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

        except Exception as e:
            log.error(f"Learn error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Learn failed: {e}")

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

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        user_id = update.message.from_user.id
        if not self._is_allowed(user_id):
            return await self._deny(update)

        chat_id = str(update.message.chat_id)
        text = update.message.text

        await update.message.chat.send_action("typing")

        try:
            response = await self.on_message("telegram", chat_id, str(user_id), text)
            if response:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
        except Exception as e:
            log.error(f"Telegram handler error: {e}")
            await update.message.reply_text(f"Error: {e}")

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
        }
        for cmd, handler in commands.items():
            self.app.add_handler(CommandHandler(cmd, handler))

        # Regular text messages
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

        # Set bot menu commands
        try:
            await self.app.bot.set_my_commands([
                BotCommand("help", "Show available commands"),
                BotCommand("evolve", "Scan signals + build skills"),
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
                BotCommand("gc", "Garbage collection + health check"),
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
