"""Cron / loop command handlers, extracted as a mixin."""
from __future__ import annotations
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .cron_core import CRON_DIR, CRON_JOBS_FILE, load_cron_jobs, save_cron_jobs, parse_interval

log = logging.getLogger(__name__)

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class CronMixin:

    async def _handle_loop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--model": {"type": "value"},
            "--max-runs": {"type": "value", "cast": int},
            "--start-now": {"type": "bool"},
        })

        args = " ".join(raw_args)
        if not args:
            await update.message.reply_text(
                "*Usage:* `/loop <interval> <prompt>`\n\n"
                "*Options:*\n"
                "`--model <name>` — override model for this loop\n"
                "`--max-runs <n>` — auto-stop after N runs\n"
                "`--start-now` — run first iteration immediately\n\n"
                "*Examples:*\n"
                "`/loop 2h scan HN for AI tools`\n"
                "`/loop 30m check GitHub trending`\n"
                "`/loop 1d --model haiku summarize today's tech news`\n"
                "`/loop 6h --max-runs 3 --start-now check for new releases`\n\n"
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

        jobs = load_cron_jobs()

        job_id = uuid.uuid4().hex[:8]
        chat_id = str(update.message.chat_id)
        now = datetime.now(timezone.utc)

        start_now = flags["--start-now"]
        next_run = now if start_now else (now + timedelta(seconds=interval_seconds))

        job = {
            "id": job_id,
            "prompt": prompt,
            "schedule_type": "interval",
            "interval_seconds": interval_seconds,
            "deliver_to": "telegram",
            "deliver_chat_id": chat_id,
            "created_at": now.isoformat(),
            "next_run_at": next_run.isoformat(),
            "run_count": 0,
            "paused": False,
            "last_run_at": None,
        }
        if flags["--model"]:
            job["model"] = flags["--model"]
        if flags["--max-runs"]:
            job["max_runs"] = flags["--max-runs"]
        jobs.append(job)
        save_cron_jobs(jobs)

        unit_names = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
        extras = []
        if flags["--model"]:
            extras.append(f"model: {flags['--model']}")
        if flags["--max-runs"]:
            extras.append(f"max runs: {flags['--max-runs']}")
        if start_now:
            extras.append("starts immediately")
        extra_line = f"\n{', '.join(extras)}" if extras else ""
        await update.message.reply_text(
            f"Loop created: `{job_id}`\n"
            f"Every {value} {unit_names[unit]}: {prompt}\n"
            f"Next run: {job['next_run_at'][:19]}{extra_line}",
            parse_mode="Markdown"
        )

    # ── /loops — list active cron jobs ───────────────────────────

    async def _handle_loops(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        jobs = load_cron_jobs()
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

        jobs = load_cron_jobs()
        new_jobs = [j for j in jobs if j.get("id") != job_id]
        if len(new_jobs) == len(jobs):
            return await update.message.reply_text(f"Loop `{job_id}` not found.", parse_mode="Markdown")

        save_cron_jobs(new_jobs)
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

        # If replying to a message with just a delay, use the replied message as reminder text
        reply_text, _ = self._get_reply_context(update)

        if not args:
            await update.message.reply_text(
                "Usage: /notify <delay> <message>\n\n"
                "Examples:\n"
                "/notify 60s check if build finished\n"
                "/notify 30m check deployment status\n"
                "/notify 2h review PR feedback\n"
                "/notify 1d renew API key\n\n"
                "Tip: Reply to a message with `/notify 30m` to be reminded about it"
            )
            return

        parts = args.split(None, 1)
        if len(parts) < 2:
            if reply_text:
                # User replied to a message with just a delay — use replied text as reminder
                delay_str = parts[0]
                message = f"Reminder about: {reply_text[:500]}"
            else:
                return await update.message.reply_text("Need delay and message. Example: `/notify 30m check the build`", parse_mode="Markdown")
        else:
            delay_str, message = parts[0], parts[1].strip()
        match = re.fullmatch(r"(\d+)(s|m|h|d)", delay_str.lower())
        if not match:
            return await update.message.reply_text(f"Invalid delay `{delay_str}`. Use `60s`, `30m`, `2h`, `1d`.", parse_mode="Markdown")

        value, unit = int(match.group(1)), match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        delay_seconds = value * multipliers[unit]

        jobs = load_cron_jobs()

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
        save_cron_jobs(jobs)

        unit_names = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
        await update.message.reply_text(
            f"Reminder set: {job_id}\n"
            f"In {value} {unit_names[unit]}: {message}\n"
            f"Will fire at: {run_at.strftime('%H:%M UTC')}"
        )

    # ── /pause & /unpause ────────────────────────────────────────

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
        """Shared logic for pause/unpause. Supports --all to toggle all jobs."""
        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--all": {"aliases": ["all"], "type": "bool"}})
        toggle_all = flags["--all"]
        job_id = raw_args[0] if raw_args else ""

        action = "pause" if paused else "unpause"
        if not job_id and not toggle_all:
            return await update.message.reply_text(
                f"Usage: /{action} <job_id>\n"
                f"       /{action} --all\n\nUse /loops to see job IDs."
            )

        jobs = load_cron_jobs()
        if not jobs:
            return await update.message.reply_text("No jobs configured.")

        if toggle_all:
            count = 0
            for job in jobs:
                if job.get("paused") != paused:
                    job["paused"] = paused
                    count += 1
            save_cron_jobs(jobs)
            past = "Paused" if paused else "Unpaused"
            return await update.message.reply_text(f"{past} {count} job(s).")

        found = False
        for job in jobs:
            if job.get("id") == job_id:
                job["paused"] = paused
                found = True
                break

        if not found:
            return await update.message.reply_text(f"Job not found: {job_id}")

        save_cron_jobs(jobs)
        past = "Paused" if paused else "Unpaused"
        await update.message.reply_text(f"{past} job: {job_id}")
