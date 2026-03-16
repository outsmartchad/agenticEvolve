"""Admin command handlers mixin — extracted from TelegramAdapter."""
from __future__ import annotations
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"
CRON_DIR = EXODIR / "cron"
CRON_JOBS_FILE = CRON_DIR / "jobs.json"

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class AdminMixin:

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
            "/cost [--week] — Today's cost (add --week for weekly)\n"
            "/config — View runtime config\n"
            "/heartbeat — Check if bot is alive\n\n"
            "Sessions\n"
            "/newsession [title] — Start new session (optionally named)\n"
            "/sessions [--limit N] — Recent sessions\n"
            "/search <query> [--limit N] — FTS5 search past sessions\n\n"
            "Memory & Identity\n"
            "/memory — Show bounded memory\n"
            "/soul — View agent personality\n\n"
            "Evolution\n"
            "/evolve [--dry-run] [--model X] [--skip-security-scan]\n"
            "/absorb <target> [--dry-run] [--model X] [--skip-security-scan]\n"
            "/learn <target> [--dry-run] [--model X] [--skip-security-scan]\n"
            "/learnings [query] [--limit N] — View past findings\n\n"
            "Skills\n"
            "/skills — List installed skills\n"
            "/queue — Skills pending approval\n"
            "/approve <name> [--force] — Install a queued skill\n"
            "/reject <name> [reason] — Remove a queued skill\n"
            "/scanskills — AgentShield security scan of all installed skills\n\n"
            "Scheduling\n"
            "/loop <interval> <prompt> [--model X] [--max-runs N] [--start-now]\n"
            "/loops — List active loops\n"
            "/unloop <id> — Cancel a loop\n"
            "/pause <id|--all> — Pause loop(s)\n"
            "/unpause <id|--all> — Resume loop(s)\n"
            "/notify <delay> <msg> — One-shot reminder\n\n"
            "Voice\n"
            "/speak <text> [--voice <name>] — Text-to-speech\n"
            "/speak --voices [lang] — List available voices\n"
            "/speak --mode <off|always|inbound> — Auto-TTS mode\n"
            "Send a voice message — auto-transcribe + reply\n\n"
            "Ideas\n"
            "/produce [--ideas N] [--model X] — Brainstorm business ideas from all signals\n\n"
            "Platform Digests\n"
            "/wechat [--hours N] [--model X] — WeChat group chat digest\n"
            "/discord [--hours N] [--model X] — Discord channel digest (subscribed)\n"
            "/whatsapp — WhatsApp digest (coming soon)\n"
            "/absorb wechat [--hours N] — Deep absorb from group chats\n\n"
            "Monitoring\n"
            "/subscribe — Select channels/users to monitor for digests\n"
            "/serve — Select channels/users for the agent to actively respond in\n\n"
            "Briefings\n"
            "/digest [--days N] — Morning briefing\n\n"
            "Maintenance\n"
            "/gc [--dry-run] — Garbage collection\n\n"
            "Settings\n"
            "/lang [code] — Set output language (zh, en, ja, ko, ...)\n\n"
            "Natural Language\n"
            "/do <instruction> [--preview] — Parse intent + run command\n\n"
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

        # Autonomy status (ZeroClaw pattern)
        from ..autonomy import format_autonomy_status
        gw = self._gateway
        cfg = gw.config if gw else {}
        autonomy_info = format_autonomy_status(cfg) if cfg else "Autonomy: unknown"

        current_model = cfg.get("model", "sonnet") if cfg else "sonnet"

        text = (
            f"*agenticEvolve status*\n\n"
            f"Gateway: running\n"
            f"Model: {current_model}\n"
            f"Memory: {mem_chars}/2200 chars\n"
            f"User profile: {user_chars}/1375 chars\n"
            f"Sessions: {s['total_sessions']} total, {s['total_messages']} msgs\n"
            f"Skills: {skill_count} installed\n"
            f"Cron jobs: {active_jobs} active\n"
            f"DB: {s['db_size_mb']} MB\n"
            f"Cost today: ${today_cost:.2f}\n\n"
            f"{autonomy_info}"
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

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--limit": {"type": "value", "cast": int, "default": 10}})
        limit = min(flags["--limit"], 50)

        from ..session_db import list_sessions
        rows = list_sessions(limit=limit)
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

        title = " ".join(context.args) if context.args else ""
        if not title:
            reply_text, _ = self._get_reply_context(update)
            if reply_text:
                title = reply_text[:100]

        chat_id = str(update.message.chat_id)
        key = f"telegram:{chat_id}"
        if self._gateway:
            sid = self._gateway._active_sessions.pop(key, None)
            self._gateway._session_last_active.pop(key, None)
            self._gateway._session_msg_count.pop(key, None)
            self._gateway._locks.pop(key, None)
            if sid:
                from ..session_db import end_session, set_title
                end_session(sid)
            # If title provided, pre-create a titled session
            if title:
                from ..session_db import create_session, generate_session_id
                new_sid = create_session(generate_session_id(), "telegram", chat_id)
                set_title(new_sid, title)
                self._gateway._active_sessions[key] = new_sid
        msg = f"New session started: *{title}*" if title else "New session started. Send your next message."
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ── /cost ────────────────────────────────────────────────────

    async def _handle_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--week": {"type": "bool"}})

        from ..agent import get_today_cost, get_week_cost
        today_cost = get_today_cost()
        daily_cap = 5.0
        weekly_cap = 25.0
        if self._gateway:
            daily_cap = self._gateway.config.get("daily_cost_cap", 5.0)
            weekly_cap = self._gateway.config.get("weekly_cost_cap", 25.0)

        lines = [f"*Cost today*: ${today_cost:.2f} / ${daily_cap:.2f}"]
        if flags["--week"]:
            week_cost = get_week_cost()
            lines.append(f"*Cost this week*: ${week_cost:.2f} / ${weekly_cap:.2f}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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

        # Autonomy info (ZeroClaw pattern)
        from ..autonomy import format_autonomy_status
        autonomy_info = format_autonomy_status(cfg)

        text = (
            f"Configuration\n\n"
            f"Model: {model}\n"
            f"Daily cap: ${daily_cap:.2f}\n"
            f"Weekly cap: ${weekly_cap:.2f}\n"
            f"Session idle timeout: {session_idle}m\n"
            f"Cron scheduler: {'on' if cron_enabled else 'off'}\n\n"
            f"Platforms:\n" + "\n".join(platforms) + "\n\n"
            f"{autonomy_info}"
        )
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

    # ── /autonomy — view/change autonomy level ───────────────────

    async def _handle_autonomy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View or change autonomy level. Usage: /autonomy [readonly|supervised|full]"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..autonomy import format_autonomy_status
        from ..config import CONFIG_PATH

        gw = self._gateway
        cfg = gw.config if gw else {}
        raw_args = list(context.args) if context.args else []

        if not raw_args:
            # Just show current autonomy
            text = format_autonomy_status(cfg)
            await update.message.reply_text(text)
            return

        new_level = raw_args[0].lower()
        if new_level not in ("readonly", "supervised", "full"):
            await update.message.reply_text(
                "Usage: /autonomy [readonly|supervised|full]\n\n"
                "- readonly: read-only tools, no writes or bash\n"
                "- supervised: restricted tool set, safe bash only\n"
                "- full: unrestricted (default)"
            )
            return

        # Update config.yaml on disk
        try:
            import yaml
            config_text = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else ""
            config_data = yaml.safe_load(config_text) or {}
            config_data["autonomy"] = new_level
            CONFIG_PATH.write_text(yaml.dump(config_data, default_flow_style=False, sort_keys=False))

            # Hot-reload will pick this up on next message
            from ..config import reload_config
            new_cfg, changes = reload_config()
            if gw:
                gw.config = new_cfg

            await update.message.reply_text(
                f"Autonomy level changed to: *{new_level}*\n\n"
                f"{format_autonomy_status(new_cfg)}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"Failed to update autonomy: {e}")

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

    # ── /learnings — list/search past learnings ──────────────────

    async def _handle_learnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List past learnings or search them."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--limit": {"type": "value", "cast": int, "default": 10}})
        limit = min(flags["--limit"], 50)
        query = self._resolve_reply_target(" ".join(raw_args), update)

        from ..session_db import list_learnings, search_learnings

        if query:
            items = search_learnings(query, limit=limit)
        else:
            items = list_learnings(limit=limit)

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
