"""Telegram platform adapter using python-telegram-bot."""
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable
from .base import BasePlatformAdapter
from ..voice import text_to_speech, speech_to_text, list_voices, maybe_tts_reply, get_tts_config, TtsMode, parse_tts_directives, detect_language_voice

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
        self._user_lang: dict[str, str] = {}  # user_id -> language code, loaded from DB on first access
        self._user_lang_loaded = False

    def _get_reply_context(self, update) -> tuple[str, list[str]]:
        """Extract text and URLs from the message being replied to.

        Returns (reply_text, urls). If not a reply, returns ("", []).
        """
        if not update.message or not update.message.reply_to_message:
            return "", []
        reply_msg = update.message.reply_to_message
        reply_text = reply_msg.text or reply_msg.caption or ""
        if not reply_text:
            return "", []
        import re
        urls = re.findall(r'https?://[^\s<>\])\'"]+', reply_text)
        return reply_text[:3000], urls

    def _resolve_reply_target(self, args_text: str, update) -> str:
        """If user said 'this'/'that'/'it' and replied to a message with URLs, inject the URL.

        Returns the enriched args text.
        """
        reply_text, urls = self._get_reply_context(update)
        if not urls:
            return args_text
        # Check if user is referencing the reply with a pronoun
        pronouns = ["this", "that", "it", "the above", "above"]
        if args_text and any(w in args_text.lower() for w in pronouns):
            return args_text + " " + " ".join(urls)
        # If no args at all but reply has URLs, use the first URL
        if not args_text.strip():
            return urls[0]
        return args_text

    async def _auto_sync_to_repo(self, pipeline: str):
        """Auto-commit and push changes to the git repo after a pipeline run."""
        import subprocess as sp
        repo_dir = Path.home() / "Desktop" / "projects" / "agenticEvolve"
        if not (repo_dir / ".git").exists():
            return

        try:
            # Sync skills from ~/.claude/skills/ to repo
            skills_src = Path.home() / ".claude" / "skills"
            skills_dst = repo_dir / "skills"
            if skills_src.exists():
                import shutil
                # Sync each skill dir
                for skill_dir in skills_src.iterdir():
                    if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                        dst = skills_dst / skill_dir.name
                        dst.mkdir(parents=True, exist_ok=True)
                        for f in skill_dir.iterdir():
                            if f.name.startswith("."):
                                continue
                            shutil.copy2(str(f), str(dst / f.name))

            # Sync gateway code
            gateway_src = Path.home() / ".agenticEvolve" / "gateway"
            gateway_dst = repo_dir / "gateway"
            if gateway_src.exists() and gateway_dst.exists():
                import shutil
                for f in gateway_src.glob("*.py"):
                    shutil.copy2(str(f), str(gateway_dst / f.name))
                platforms_src = gateway_src / "platforms"
                platforms_dst = gateway_dst / "platforms"
                if platforms_src.exists():
                    platforms_dst.mkdir(parents=True, exist_ok=True)
                    for f in platforms_src.glob("*.py"):
                        shutil.copy2(str(f), str(platforms_dst / f.name))

            # Git add, commit, push
            sp.run(["git", "add", "-A"], cwd=str(repo_dir), capture_output=True, timeout=30)
            diff = sp.run(["git", "diff", "--cached", "--stat"], cwd=str(repo_dir), capture_output=True, text=True, timeout=10)
            if diff.stdout.strip():
                sp.run(
                    ["git", "commit", "-m", f"auto: sync after /{pipeline} pipeline"],
                    cwd=str(repo_dir), capture_output=True, timeout=30
                )
                sp.run(["git", "push"], cwd=str(repo_dir), capture_output=True, timeout=60)
                log.info(f"Auto-synced to repo after /{pipeline}")
            else:
                log.info(f"No changes to sync after /{pipeline}")
        except Exception as e:
            log.error(f"Auto-sync failed after /{pipeline}: {e}")

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

    @staticmethod
    def _parse_flags(raw_args: list, flag_defs: dict) -> dict:
        """Parse flags from args list. Mutates raw_args (removes consumed flags).

        flag_defs: dict mapping flag names to their config:
          {"--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
           "--model": {"type": "value"},  # consumes next arg
           "--limit": {"type": "value", "cast": int, "default": 10}}

        Returns dict of parsed flag values.
        """
        result = {}
        for flag, cfg in flag_defs.items():
            flag_type = cfg.get("type", "bool")
            aliases = [flag] + cfg.get("aliases", [])

            if flag_type == "bool":
                result[flag] = False
                for alias in aliases:
                    if alias in raw_args:
                        result[flag] = True
                        raw_args.remove(alias)
                        break

            elif flag_type == "value":
                result[flag] = cfg.get("default")
                for alias in aliases:
                    if alias in raw_args:
                        idx = raw_args.index(alias)
                        if idx + 1 < len(raw_args):
                            val = raw_args[idx + 1]
                            cast = cfg.get("cast")
                            try:
                                result[flag] = cast(val) if cast else val
                            except (ValueError, TypeError):
                                result[flag] = cfg.get("default")
                            raw_args.pop(idx + 1)
                        raw_args.pop(idx)
                        break
        return result

    # ── Language preference ─────────────────────────────────────

    LANG_NAMES = {
        "zh": "Simplified Chinese (简体中文)",
        "zh-tw": "Traditional Chinese (繁體中文)",
        "en": "English",
        "ja": "Japanese (日本語)",
        "ko": "Korean (한국어)",
        "es": "Spanish (Español)",
        "fr": "French (Français)",
        "de": "German (Deutsch)",
        "pt": "Portuguese (Português)",
        "ru": "Russian (Русский)",
    }

    def _load_user_lang(self, user_id: str) -> str | None:
        """Load language preference from DB into cache. Returns the lang code or None."""
        if user_id in self._user_lang:
            return self._user_lang[user_id]
        try:
            from ..session_db import get_user_pref
            lang = get_user_pref(str(user_id), "lang")
            if lang:
                self._user_lang[user_id] = lang
            return lang
        except Exception:
            return None

    def _get_lang_instruction(self, user_id: str) -> str:
        """Return a prompt suffix for the user's preferred language, or '' if unset/English."""
        lang = self._load_user_lang(str(user_id))
        if not lang or lang == "en":
            return ""
        name = self.LANG_NAMES.get(lang, lang)
        return f"\n\nIMPORTANT: Write your ENTIRE response in {name}."

    async def _handle_lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set or view your preferred output language. Persisted to DB.

        Usage: /lang [code]  — e.g. /lang zh, /lang en, /lang ja
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        user_id = str(update.message.from_user.id)
        args = context.args if context.args else []

        if not args:
            current = self._load_user_lang(user_id) or "en"
            name = self.LANG_NAMES.get(current, current)
            codes = ", ".join(f"`{k}`" for k in sorted(self.LANG_NAMES))
            await update.message.reply_text(
                f"*Current language:* {name} (`{current}`)\n\n"
                f"*Set:* `/lang <code>`\n"
                f"Codes: {codes}\n\n"
                f"This affects all long-running commands (/produce, /learn, /evolve, /absorb, /wechat).",
                parse_mode="Markdown"
            )
            return

        code = args[0].lower().strip()
        if code == "reset" or code == "off":
            self._user_lang.pop(user_id, None)
            try:
                from ..session_db import delete_user_pref
                delete_user_pref(user_id, "lang")
            except Exception:
                pass
            await update.message.reply_text("Language reset to English.")
            return

        self._user_lang[user_id] = code
        try:
            from ..session_db import set_user_pref
            set_user_pref(user_id, "lang", code)
        except Exception:
            pass
        name = self.LANG_NAMES.get(code, code)
        await update.message.reply_text(f"Output language set to: {name} (`{code}`)", parse_mode="Markdown")

    def _make_progress_tracker(self, chat_id: str, loop, pipeline_stages: list[str] | None = None):
        """Create a live-editing progress tracker for long-running commands.

        One Telegram message is edited in-place every 3s. Shows:
        - Stage pipeline with current position highlighted
        - Last 12 tool actions
        - Elapsed time + step count

        Returns (on_progress_sync, get_tool_count, start_reporter, stop_reporter).
        """
        import time

        _TOOL_PREFIX = {
            "Bash": "$",
            "Read": "r",
            "Write": "w",
            "Edit": "e",
            "Glob": "g",
            "Grep": "g",
            "WebFetch": "f",
            "Task": "a",
            "TodoRead": "t",
            "TodoWrite": "t",
            "Agent": "a",
            "WebSearch": "s",
        }

        # Stage emoji for known pipeline stages
        _STAGE_ICON = {
            "collect": "1/5",
            "analyze": "2/5",
            "build": "3/5",
            "review": "4/5",
            "report": "5/5",
            "scan": "1/5",
            "gap": "2/5",
            "plan": "3/5",
            "implement": "4/5",
            "security scan": "scan",
        }

        stages = pipeline_stages or []

        state = {
            "tool_count": 0,
            "tool_lines": [],
            "stage": "",
            "stages_seen": [],
            "done": False,
            "dirty": False,
            "msg_id": None,
            "reporter_task": None,
            "start_time": time.time(),
        }

        def on_progress_sync(text: str):
            """Called from sync thread — track state, mark dirty for edit."""
            # Stage transitions
            if text.startswith("*Stage:") or text.startswith("*Security scan:"):
                stage_name = text.replace("*", "").strip()
                state["stage"] = stage_name
                if stage_name not in state["stages_seen"]:
                    state["stages_seen"].append(stage_name)
                state["tool_lines"].append(f"-- {stage_name} --")
                state["dirty"] = True
                return

            # Pipeline-level status (asterisk prefix, not a stage)
            if text.startswith("*"):
                stage_name = text.replace("*", "").strip()
                state["stage"] = stage_name
                return

            # Tool-use events
            if text.startswith("[") and "] " in text[:12]:
                state["tool_count"] += 1
                after_bracket = text.split("] ", 1)[1] if "] " in text else text
                if ": " in after_bracket:
                    action, preview = after_bracket.split(": ", 1)
                    preview = preview.strip("`").strip()[:55]
                    prefix = _TOOL_PREFIX.get(action.strip(), action.strip().lower()[:4])
                    line = f"  [{prefix}] {preview}"
                else:
                    line = f"  {after_bracket.strip()[:60]}"
                state["tool_lines"].append(line)
                state["dirty"] = True

        def _fmt_elapsed(secs: int) -> str:
            if secs < 60:
                return f"{secs}s"
            return f"{secs // 60}m{secs % 60:02d}s"

        def _stage_bar() -> str:
            """Build compact stage progress indicator."""
            if not stages:
                return ""
            current = state["stage"].lower()
            parts = []
            for s in stages:
                sl = s.lower()
                if sl in current or current in sl:
                    parts.append(f"[{s.upper()}]")
                elif any(sl in seen.lower() or seen.lower() in sl for seen in state["stages_seen"]):
                    parts.append(s.lower())
                else:
                    parts.append(s.lower())
            return " > ".join(parts)

        async def _build_status_text() -> str:
            elapsed = int(time.time() - state["start_time"])
            tc = state["tool_count"]
            stage = state["stage"] or "starting"

            # Determine stage icon
            stage_lower = stage.lower()
            icon = ""
            for key, val in _STAGE_ICON.items():
                if key in stage_lower:
                    icon = f" ({val})"
                    break

            header = f"{stage}{icon}  |  {tc} steps  {_fmt_elapsed(elapsed)}"

            bar = _stage_bar()
            bar_line = f"\n{bar}" if bar else ""

            recent = state["tool_lines"][-12:]
            if len(state["tool_lines"]) > 12:
                skipped = len(state["tool_lines"]) - 12
                recent = [f"  ... +{skipped} earlier"] + recent
            body = "\n".join(recent) if recent else ""

            parts = [header]
            if bar_line:
                parts.append(bar_line)
            if body:
                parts.append(body)
            return "\n".join(parts)

        async def _reporter_loop():
            """Edit the status message every 3s when dirty, 15s heartbeat."""
            last_edit = 0.0
            while not state["done"]:
                await asyncio.sleep(3)
                if state["done"]:
                    break
                now = time.time()
                if state["dirty"] or (now - last_edit >= 15):
                    state["dirty"] = False
                    text = await _build_status_text()
                    try:
                        if state["msg_id"] is None:
                            msg = await self.app.bot.send_message(
                                chat_id=int(chat_id), text=text
                            )
                            state["msg_id"] = msg.message_id
                        else:
                            await self.app.bot.edit_message_text(
                                chat_id=int(chat_id),
                                message_id=state["msg_id"],
                                text=text,
                            )
                        last_edit = now
                    except Exception as e:
                        if "not modified" not in str(e).lower():
                            log.debug(f"Progress edit failed: {e}")
                    try:
                        await self.app.bot.send_chat_action(
                            chat_id=int(chat_id), action="typing"
                        )
                    except Exception:
                        pass

        def start_reporter():
            state["done"] = False
            state["start_time"] = time.time()
            state["reporter_task"] = asyncio.ensure_future(_reporter_loop())

        def stop_reporter():
            state["done"] = True
            if state["reporter_task"]:
                state["reporter_task"].cancel()

        def get_tool_count():
            return state["tool_count"]

        return on_progress_sync, get_tool_count, start_reporter, stop_reporter

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
            "/reject <name> [reason] — Remove a queued skill\n\n"
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
            "WeChat\n"
            "/wechat [--hours N] [--model X] — Group chat digest\n"
            "/absorb wechat [--hours N] — Deep absorb from group chats\n\n"
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
                from ..session_db import end_session, set_session_title
                end_session(sid)
            # If title provided, pre-create a titled session
            if title:
                from ..session_db import create_session
                new_sid = create_session("telegram", chat_id)
                set_session_title(new_sid, title)
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

    # ── /evolve ──────────────────────────────────────────────────

    async def _handle_evolve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run multi-stage evolve pipeline with live progress."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
            "--skip-security-scan": {"type": "bool"},
            "--model": {"type": "value"},
        })
        dry_run = flags["--dry-run"]
        skip_security_scan = flags["--skip-security-scan"]
        model_override = flags["--model"]

        chat_id = str(update.message.chat_id)
        if dry_run:
            await update.message.reply_text(
                "Dry run: COLLECT → ANALYZE (stops before building)\n"
                "~2-4 min",
            )
        else:
            await update.message.reply_text(
                "Evolving... COLLECT → ANALYZE → BUILD → REVIEW → REPORT\n"
                "~5-10 min. Progress below.",
            )

        loop = asyncio.get_running_loop()
        _stages = ["collect", "analyze"] if dry_run else ["collect", "analyze", "build", "review", "report"]
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop, pipeline_stages=_stages)

        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        start_reporter()
        try:
            from ..evolve import EvolveOrchestrator

            orchestrator = EvolveOrchestrator(
                model=model,
                on_progress=on_progress_sync,
                skip_security_scan=skip_security_scan,
            )

            summary, cost = await loop.run_in_executor(
                None, lambda: orchestrator.run(dry_run=dry_run)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Evolve error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Evolution failed: {e}")
            return
        finally:
            stop_reporter()

        # Send single comprehensive report
        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_summary = summary + footer
        for i in range(0, len(full_summary), 4000):
            chunk = full_summary[i:i+4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk
                )

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "evolve", cost)

        # Auto-commit and push new skills to git repo
        await self._auto_sync_to_repo("evolve")

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

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--force": {"aliases": ["force"], "type": "bool"}})
        if not raw_args:
            return await update.message.reply_text("Usage: `/approve <skill-name> [--force]`", parse_mode="Markdown")

        name = raw_args[0]
        force = flags["--force"]

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
        CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))

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

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--skip-security-scan": {"type": "bool"},
            "--model": {"type": "value"},
            "--dry-run": {"aliases": ["dry-run", "preview"], "type": "bool"},
        })
        skip_security_scan = flags["--skip-security-scan"]
        model_override = flags["--model"]
        dry_run = flags["--dry-run"]

        target = self._resolve_reply_target(" ".join(raw_args), update)
        if not target:
            await update.message.reply_text(
                "*Usage:* `/learn <repo-url or tech name>`\n\n"
                "*Options:*\n"
                "`--dry-run` — security scan + preview only, no full analysis\n"
                "`--model <name>` — override model (e.g. opus for deeper analysis)\n"
                "`--skip-security-scan` — bypass security check\n\n"
                "*Examples:*\n"
                "`/learn https://github.com/vercel/ai`\n"
                "`/learn --model opus anthropic tool-use patterns`\n"
                "`/learn --dry-run https://github.com/nicepkg/aide`\n\n"
                "Tip: Reply to a message containing a URL and just send `/learn`",
                parse_mode="Markdown"
            )
            return

        short_target = target[:60] + ("..." if len(target) > 60 else "")
        if dry_run:
            await update.message.reply_text(
                f"Learning (preview): {short_target}\n~1-2 min. Security scan only.",
            )
        else:
            await update.message.reply_text(
                f"Learning: {short_target}\n~3-6 min. Progress below.",
            )

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        loop = asyncio.get_running_loop()

        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop, pipeline_stages=["fetch", "analyze", "extract"])

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
            f"- Create a skill directly in ~/.claude/skills/<name>/SKILL.md with concrete instructions\n"
            f"- Include a Source: <url> line at the bottom of the SKILL.md\n"
            f"- Install it directly — no queue, no approval needed\n\n"
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

        # Security scan for GitHub repos: clone first, scan, then proceed
        if is_github and not skip_security_scan:
            self._report_sync = on_progress_sync
            security_blocked = await self._security_prescan_github(target, chat_id, loop)
            if security_blocked:
                return
        elif is_github and skip_security_scan:
            on_progress_sync("*Security scan: skipped (--skip-security-scan)*")

        if is_github:
            learn_prompt = (
                system_context +
                f"Deep-dive this GitHub repo: {target}\n\n"
                f"The repo has been pre-cloned to /tmp/learn-scan/ and passed security scan.\n"
                f"1. Read the repo from /tmp/learn-scan/\n"
                f"2. Read the README, key source files, and architecture\n"
                f"3. Understand how it works — focus on the interesting engineering, not surface features\n\n"
                f"SECURITY: Do NOT run any install scripts, build commands, or execute code from this repo. "
                f"READ ONLY. Do not run npm install, pip install, make, or any setup scripts.\n\n"
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

        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        # Inject language preference into prompt
        lang_instruction = self._get_lang_instruction(user_id)
        if lang_instruction:
            learn_prompt += lang_instruction

        # Dry run: show security scan result and what would be analyzed, then stop
        if dry_run:
            lines = [f"*Learn dry run: {target}*\n"]
            lines.append(f"Type: {'GitHub repo' if is_github else 'URL' if is_url else 'topic'}")
            lines.append(f"Model: {model}")
            lines.append(f"Security scan: {'skipped' if skip_security_scan else 'passed'}")
            lines.append(f"\nWould run full analysis with Claude ({model}).")
            lines.append(f"Run `/learn {target}` to execute.")
            await self.app.bot.send_message(chat_id=int(chat_id), text="\n".join(lines))
            return

        start_reporter()
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
        except Exception as e:
            stop_reporter()
            log.error(f"Learn error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Learn failed: {e}")
            return
        finally:
            stop_reporter()

        response = result.get("text", "No output.")
        cost = result.get("cost", 0)
        tools_used = get_tool_count()

        # Send single comprehensive report
        header = f"*Learn: {target}*\n({tools_used} steps, ${cost:.2f})\n\n"
        full = header + response
        for i in range(0, len(full), 4000):
            chunk = full[i:i+4000]
            try:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk, parse_mode="Markdown")
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "learn", cost)

        # Auto-sync to repo
        await self._auto_sync_to_repo("learn")

        # Store learning in DB
        try:
            from ..session_db import add_learning
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

    # ── /absorb — deep scan + implement improvements ───────────

    async def _handle_absorb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deep scan a target, analyze gaps in our system, and implement improvements."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
            "--skip-security-scan": {"type": "bool"},
            "--model": {"type": "value"},
        })
        dry_run = flags["--dry-run"]
        skip_security_scan = flags["--skip-security-scan"]
        model_override = flags["--model"]

        target = self._resolve_reply_target(" ".join(raw_args), update)
        if not target:
            await update.message.reply_text(
                "*Usage:* `/absorb <repo-url or tech/architecture>`\n\n"
                "*Options:*\n"
                "`--dry-run` — scan + gap analysis only\n"
                "`--model <name>` — override model for this run\n"
                "`--skip-security-scan` — bypass security check\n\n"
                "*Examples:*\n"
                "`/absorb https://github.com/NousResearch/hermes-agent`\n"
                "`/absorb --model opus persistent memory protocol`\n"
                "`/absorb --dry-run https://github.com/langchain-ai/langgraph`\n\n"
                "Tip: Reply to a message containing a URL and just send `/absorb`",
                parse_mode="Markdown"
            )
            return

        is_wechat = target.lower().startswith("wechat")
        is_url = target.startswith("http://") or target.startswith("https://")
        is_github = "github.com" in target
        target_type = "wechat" if is_wechat else ("github" if is_github else ("url" if is_url else "topic"))

        short_target = target[:60] + ("..." if len(target) > 60 else "")
        if dry_run:
            await update.message.reply_text(
                f"Absorb (dry run): {short_target}\n"
                f"SCAN → GAP (stops before implementing)\n~3-5 min. Progress below.",
            )
        else:
            await update.message.reply_text(
                f"Absorbing: {short_target}\n"
                f"SCAN → GAP → PLAN → IMPLEMENT → REPORT\n~8-15 min. Progress below.",
            )

        chat_id = str(update.message.chat_id)
        loop = asyncio.get_running_loop()

        _absorb_stages = ["scan", "gap"] if dry_run else ["scan", "gap", "plan", "implement", "report"]
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop, pipeline_stages=_absorb_stages)

        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        # Security prescan for GitHub repos (Layer 1 — before handing to absorb pipeline)
        is_github = target.startswith("https://github.com/") or target.startswith("git@github.com:")
        if is_github and not skip_security_scan and not is_wechat:
            security_blocked = await self._security_prescan_github(target, chat_id, asyncio.get_running_loop())
            if security_blocked:
                return
        elif is_github and skip_security_scan:
            on_progress_sync("*Security scan: skipped (--skip-security-scan)*")

        start_reporter()
        try:
            from ..absorb import AbsorbOrchestrator

            orchestrator = AbsorbOrchestrator(
                target=target,
                target_type=target_type,
                model=model,
                on_progress=on_progress_sync,
                skip_security_scan=skip_security_scan,
            )

            summary, cost = await loop.run_in_executor(
                None, lambda: orchestrator.run(dry_run=dry_run)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Absorb error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Absorb failed: {e}")
            return
        finally:
            stop_reporter()

        # Send single comprehensive report
        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_summary = summary + footer
        for i in range(0, len(full_summary), 4000):
            chunk = full_summary[i:i+4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk
                )

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "absorb", cost)

        # Auto-sync to repo
        await self._auto_sync_to_repo("absorb")

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

    # ── /learnings — view past learnings ────────────────────────

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

    # ── /gc — garbage collection ────────────────────────────────

    async def _handle_gc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run garbage collection — clean stale sessions, orphan skills, check memory health."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"}})
        dry_run = flags["--dry-run"]

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
        """Search past sessions using FTS5. Usage: /search <query> [--limit N]"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--limit": {"type": "value", "cast": int, "default": 5}})
        limit = min(flags["--limit"], 20)
        query = self._resolve_reply_target(" ".join(raw_args), update)
        if not query:
            await update.message.reply_text(
                "Usage: /search <query> [--limit N]\n\n"
                "Examples:\n"
                "/search telegram rate limit\n"
                "/search --limit 10 cost cap\n"
                "/search absorb pipeline\n\n"
                "Tip: Reply to a message and send /search to search for its content"
            )
            return

        from ..session_db import search_sessions
        results = search_sessions(query, limit=limit)

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

    # ── /recall — cross-layer unified search ────────────────────

    async def _handle_recall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search across ALL memory layers: sessions, learnings, instincts, memory, user profile."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        query = self._resolve_reply_target(" ".join(raw_args), update)
        if not query:
            await update.message.reply_text(
                "Usage: /recall <query>\n\n"
                "Searches ALL memory layers at once:\n"
                "- Past conversations (sessions)\n"
                "- Absorbed knowledge (learnings)\n"
                "- Observed patterns (instincts)\n"
                "- Agent notes (MEMORY.md)\n"
                "- User profile (USER.md)\n\n"
                "Tip: Reply to a message with /recall to search for its content"
            )
            return

        from ..session_db import unified_search, format_recall_context

        # Get active session ID if available
        chat_id = str(update.message.chat_id)
        key = f"telegram:{chat_id}"
        session_id = ""
        if self._gateway:
            session_id = self._gateway._active_sessions.get(key, "")

        results = unified_search(query, session_id=session_id, limit_per_layer=5)

        if not results:
            await update.message.reply_text(f"No results across any memory layer for: {query}")
            return

        # Format with source grouping
        formatted = format_recall_context(results, max_chars=3800)
        header = f"Recall: {query}\n{len(results)} results across {len(set(r.get('source','') for r in results))} layers\n"
        text = header + "\n" + formatted

        try:
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception:
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

        if not CRON_JOBS_FILE.exists():
            return await update.message.reply_text("No jobs configured.")

        try:
            jobs = json.loads(CRON_JOBS_FILE.read_text())
        except Exception:
            return await update.message.reply_text("Failed to read jobs.json.")

        if toggle_all:
            count = 0
            for job in jobs:
                if job.get("paused") != paused:
                    job["paused"] = paused
                    count += 1
            CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))
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

        CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))
        past = "Paused" if paused else "Unpaused"
        await update.message.reply_text(f"{past} job: {job_id}")

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

    async def _security_prescan_github(self, target: str, chat_id: str, loop) -> bool:
        """Clone a GitHub repo and run security scan. Returns True if blocked."""
        import subprocess as sp
        from ..security import scan_directory, format_telegram_report

        scan_path = Path("/tmp/learn-scan")

        # Clone
        try:
            sp.run(["rm", "-rf", str(scan_path)], capture_output=True, timeout=10)
            proc = sp.run(
                ["git", "clone", "--depth", "1", target, str(scan_path)],
                capture_output=True, text=True, timeout=120
            )
            if proc.returncode != 0:
                # Clone failed — let claude -p handle it
                return False
        except Exception:
            return False

        # Security scan
        result = scan_directory(scan_path, label=target)
        report = format_telegram_report(result)

        if result.verdict == "BLOCKED":
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id),
                    text=report + "\n\n/learn aborted for safety.",
                )
            except Exception:
                pass
            # Clean up
            sp.run(["rm", "-rf", str(scan_path)], capture_output=True, timeout=10)
            return True

        if result.verdict == "WARNING":
            try:
                await self.app.bot.send_message(chat_id=int(chat_id), text=report)
            except Exception:
                pass

        return False

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

            is_url = target.startswith("http://") or target.startswith("https://")
            is_github = "github.com" in target
            target_type = "github" if is_github else ("url" if is_url else "topic")
            model = self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet"

            try:
                from ..absorb import AbsorbOrchestrator

                loop = asyncio.get_running_loop()
                on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
                    self._make_progress_tracker(chat_id, loop)

                orchestrator = AbsorbOrchestrator(
                    target=target,
                    target_type=target_type,
                    model=model,
                    on_progress=on_progress_sync,
                )

                start_reporter()
                try:
                    summary, cost = await loop.run_in_executor(
                        None, lambda: orchestrator.run(dry_run=False)
                    )
                finally:
                    stop_reporter()

                tools_used = get_tool_count()
                footer = f"\n\n({tools_used} steps, ${cost:.2f})"
                full_summary = summary + footer
                for i in range(0, len(full_summary), 4000):
                    await self.app.bot.send_message(chat_id=int(chat_id), text=full_summary[i:i+4000])

                try:
                    from ..session_db import add_learning
                    add_learning(
                        target=target, target_type=target_type,
                        verdict="ABSORBED",
                        patterns="Absorbed via inline button. See full report.",
                        operational_benefit=f"System improvements implemented. Cost: ${cost:.2f}",
                        skill_created="", full_report=summary[:8000], cost=cost,
                    )
                except Exception as e:
                    log.warning(f"Failed to store absorb learning: {e}")

            except Exception as e:
                log.error(f"Callback absorb error: {e}")
                await self.app.bot.send_message(chat_id=int(chat_id), text=f"Absorb failed: {e}")

        elif data.startswith("learn:"):
            target = data[6:]
            await query.edit_message_text(f"Learning from: {target[:100]}...")

            is_url = target.startswith("http://") or target.startswith("https://")
            is_github = "github.com" in target
            target_type = "github" if is_github else ("url" if is_url else "topic")
            model = self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet"

            # Security prescan for GitHub repos
            if is_github:
                security_blocked = await self._security_prescan_github(target, chat_id, asyncio.get_running_loop())
                if security_blocked:
                    return

            try:
                from ..agent import invoke_claude_streaming, build_system_prompt

                clone_note = ""
                if is_github:
                    clone_note = (
                        f"The repo has been pre-cloned to /tmp/learn-scan/ and passed security scan.\n"
                        f"Read from /tmp/learn-scan/ instead of cloning again.\n"
                        f"SECURITY: Do NOT run install scripts, build commands, or execute any code from this repo.\n\n"
                    )

                prompt = (
                    f"Deep-dive this target and extract patterns our system can learn from:\n\n"
                    f"Target: {target}\n\n"
                    f"{clone_note}"
                    f"Focus on: what patterns can we steal, what would benefit our development workflow, "
                    f"and whether we should ADOPT (use it) / STEAL (take patterns, skip dep) / SKIP (not useful).\n\n"
                    f"At the END return a JSON block:\n"
                    f'```json\n{{"verdict": "ADOPT|STEAL|SKIP", "patterns": "...", '
                    f'"operational_benefit": "...", "skill_created": ""}}\n```'
                )

                loop = asyncio.get_running_loop()

                def _run_learn():
                    return invoke_claude_streaming(
                        message=prompt,
                        on_progress=lambda x: None,
                        model=model,
                    )

                result = await loop.run_in_executor(None, _run_learn)

                response = result.get("text", "No response")
                cost = result.get("cost", 0)
                for i in range(0, len(response), 4000):
                    await self.app.bot.send_message(chat_id=int(chat_id), text=response[i:i+4000])

                # Store learning
                try:
                    from ..session_db import add_learning
                    learning_data = {}
                    if "```json" in response:
                        json_start = response.find("```json")
                        json_end = response.find("```", json_start + 7) if json_start >= 0 else -1
                        json_str = response[json_start + 7:json_end].strip()
                        try:
                            learning_data = json.loads(json_str)
                        except (json.JSONDecodeError, ValueError):
                            pass

                    add_learning(
                        target=target, target_type=target_type,
                        verdict=learning_data.get("verdict", "UNKNOWN"),
                        patterns=learning_data.get("patterns", ""),
                        operational_benefit=learning_data.get("operational_benefit", ""),
                        skill_created=learning_data.get("skill_created", ""),
                        full_report=response[:8000], cost=cost,
                    )
                except Exception as e:
                    log.warning(f"Failed to store learning from callback: {e}")

            except Exception as e:
                log.error(f"Callback learn error: {e}")
                await self.app.bot.send_message(chat_id=int(chat_id), text=f"Learn failed: {e}")

        elif data == "chat:proceed":
            await query.edit_message_text("Got it, continuing as normal chat.")

    # ── Photo/image handler ──────────────────────────────────────

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photos sent to the bot — download and pass to Claude for vision analysis.

        Workflow:
        1. Download highest-res photo to tmp/images/
        2. Build prompt with image path + caption + reply context
        3. Send to Claude (which uses Read tool to see the image)
        4. Auto-TTS if voice mode is active
        5. Offer absorb/learn if response contains URLs
        6. Cleanup temp image file
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        caption = update.message.caption or ""

        # If photo has a URL in the caption AND no other meaningful text, offer absorb/learn
        urls = self._extract_urls(caption) if caption else []
        if urls:
            non_url_text = caption
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                # Caption is just a URL — user wants to absorb/learn, not analyze the photo
                await self._offer_absorb_learn(update, urls[0], "link in image caption")
                return

        # Download the photo (get highest resolution)
        photo = update.message.photo[-1]  # largest size
        img_dir = EXODIR / "tmp" / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        img_path = img_dir / f"{timestamp}_{photo.file_id[:8]}.jpg"

        try:
            file = await context.bot.get_file(photo.file_id)
            await file.download_to_drive(str(img_path))
            log.info(f"Photo saved: {img_path} ({photo.width}x{photo.height})")
        except Exception as e:
            log.error(f"Failed to download photo: {e}")
            await update.message.reply_text(f"Failed to download image: {e}")
            return

        # Build prompt for Claude with the image path
        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)

        # Resolve reply-to context (user may be replying to a message with a photo)
        reply_text, reply_urls = self._get_reply_context(update)

        prompt = (
            f"[The user sent an image. It is saved at: {img_path}]\n"
            f"Read this image file and analyze it.\n"
        )
        if caption:
            prompt += f"\nUser's message with the image: {caption}\n"
        if reply_text:
            prompt += f"\n[This was sent as a reply to: {reply_text[:1500]}]\n"
        if not caption:
            prompt += (
                "\nDescribe what you see. If it's a screenshot of a tool, library, repo, "
                "or technical content, extract the key info (name, URL, purpose). "
                "If it contains code, transcribe and explain it."
            )

        # Keep typing indicator alive
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
            response = await self.on_message("telegram", chat_id, user_id, prompt)
            if response:
                # Check TTS auto-mode
                config = self._gateway.config if self._gateway else {}
                audio_reply, clean_response = await maybe_tts_reply(response, config, inbound_was_voice=False)

                # Check if response mentions a URL or tool — offer absorb/learn
                resp_urls = self._extract_urls(clean_response)

                if audio_reply and audio_reply.exists():
                    try:
                        for i in range(0, len(clean_response), 4000):
                            await update.message.reply_text(clean_response[i:i+4000])
                        with open(audio_reply, "rb") as af:
                            await update.message.reply_voice(voice=af)
                    except Exception as e:
                        log.warning(f"Failed to send TTS reply for photo: {e}")
                    finally:
                        audio_reply.unlink(missing_ok=True)
                else:
                    for i in range(0, len(clean_response), 4000):
                        await update.message.reply_text(clean_response[i:i+4000])

                if resp_urls:
                    await self._offer_absorb_learn(update, resp_urls[0], "tool/repo detected in image")
        except Exception as e:
            log.error(f"Photo processing error: {e}")
            await update.message.reply_text(f"Error processing image: {e}")
        finally:
            typing_active = False
            typing_task.cancel()
            # Cleanup temp image
            try:
                img_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ── Document/file handler ──────────────────────────────────────

    async def _handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle documents sent to the bot — download and pass to Claude for analysis.

        Supports: PDFs, code files, text files, images sent as documents, etc.
        Claude's Read tool can handle images, PDFs, and text files natively.

        Workflow:
        1. Download document to tmp/documents/
        2. Build prompt with file path + caption + reply context
        3. Send to Claude (which uses Read tool to analyze the file)
        4. Offer absorb/learn if response contains URLs
        5. Cleanup temp file
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        doc = update.message.document
        if not doc:
            return

        caption = update.message.caption or ""

        # If caption is just a URL, offer absorb/learn
        urls = self._extract_urls(caption) if caption else []
        if urls:
            non_url_text = caption
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                await self._offer_absorb_learn(update, urls[0], "link in document caption")
                return

        # Size guard — skip files > 50MB
        file_size = doc.file_size or 0
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(
                f"File too large ({file_size / 1024 / 1024:.1f} MB). Max supported: 50 MB."
            )
            return

        # Download the document
        doc_dir = EXODIR / "tmp" / "documents"
        doc_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        original_name = doc.file_name or "unnamed"
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in original_name)
        doc_path = doc_dir / f"{timestamp}_{safe_name}"

        try:
            file = await context.bot.get_file(doc.file_id)
            await file.download_to_drive(str(doc_path))
            log.info(f"Document saved: {doc_path} ({file_size} bytes, mime={doc.mime_type})")
        except Exception as e:
            log.error(f"Failed to download document: {e}")
            await update.message.reply_text(f"Failed to download file: {e}")
            return

        # Build prompt for Claude with the file path
        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)

        # Resolve reply-to context
        reply_text, reply_urls = self._get_reply_context(update)

        # Determine file type hint
        mime = doc.mime_type or ""
        if mime.startswith("image/"):
            file_hint = "image file"
        elif mime == "application/pdf":
            file_hint = "PDF document"
        elif mime.startswith("text/") or mime in ("application/json", "application/xml", "application/javascript"):
            file_hint = "text/code file"
        elif any(safe_name.endswith(ext) for ext in (".py", ".ts", ".js", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".sol", ".md", ".txt", ".csv", ".toml", ".yaml", ".yml", ".json", ".xml", ".html", ".css", ".sh", ".sql")):
            file_hint = "text/code file"
        else:
            file_hint = f"file (MIME: {mime})" if mime else "file"

        prompt = (
            f"[The user sent a {file_hint}: \"{original_name}\" saved at: {doc_path}]\n"
            f"Read this file and analyze its contents.\n"
        )
        if caption:
            prompt += f"\nUser's message with the file: {caption}\n"
        if reply_text:
            prompt += f"\n[This was sent as a reply to: {reply_text[:1500]}]\n"
        if not caption:
            prompt += (
                "\nProvide a summary of the file contents. If it's code, explain what it does. "
                "If it's a PDF or document, extract key information. "
                "If it's an image, describe what you see."
            )

        # Keep typing indicator alive
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
            response = await self.on_message("telegram", chat_id, user_id, prompt)
            if response:
                # Check if response mentions a URL or tool — offer absorb/learn
                resp_urls = self._extract_urls(response)
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
                if resp_urls:
                    await self._offer_absorb_learn(update, resp_urls[0], "tool/repo detected in document")
        except Exception as e:
            log.error(f"Document processing error: {e}")
            await update.message.reply_text(f"Error processing file: {e}")
        finally:
            typing_active = False
            typing_task.cancel()
            # Cleanup temp document
            try:
                doc_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ── /screenshot — capture URL and send as photo ───────────────

    async def _handle_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Capture a URL screenshot and send it as a Telegram photo.

        Usage:
            /screenshot <url>           — screenshot at 1280x800
            /screenshot <url> --full    — full-page screenshot
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = list(context.args) if context.args else []
        if not args:
            await update.message.reply_text(
                "Usage: /screenshot <url> [--full]\n"
                "Example: /screenshot https://example.com"
            )
            return

        full_page = "--full" in args
        url = next((a for a in args if not a.startswith("--")), None)
        if not url:
            await update.message.reply_text("Please provide a URL.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        status_msg = await update.message.reply_text(f"Screenshotting {url} ...")

        try:
            from playwright.async_api import async_playwright
            import tempfile

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(url, wait_until="networkidle", timeout=30000)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    tmp_path = f.name
                await page.screenshot(path=tmp_path, full_page=full_page)
                await browser.close()

            with open(tmp_path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=url[:1024],
                )
            Path(tmp_path).unlink(missing_ok=True)
            await status_msg.delete()

        except Exception as e:
            log.error(f"Screenshot failed for {url}: {e}")
            await status_msg.edit_text(f"Screenshot failed: {e}")

    async def send_photo(self, chat_id: str, image_bytes: bytes, caption: str = "") -> None:
        """Send an image to a Telegram chat."""
        if self.app and self.app.bot:
            import io
            await self.app.bot.send_photo(
                chat_id=int(chat_id),
                photo=io.BytesIO(image_bytes),
                caption=caption[:1024] if caption else "",
            )

    # ── /restart — remote gateway restart ────────────────────────

    async def _handle_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restart the gateway process remotely via Telegram."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        await update.message.reply_text("Restarting gateway in 2s...")

        # Write a restart script to /tmp, then execute it detached.
        # This avoids pkill matching the script's own command line.
        import subprocess as sp
        restart_sh = Path("/tmp/ae-restart.sh")
        restart_sh.write_text(
            "#!/bin/bash\n"
            "sleep 2\n"
            "# Kill gateway by PID file or process match\n"
            "PID=$(pgrep -f 'python3 -m gateway.run')\n"
            "if [ -n \"$PID\" ]; then kill -9 $PID; fi\n"
            "sleep 1\n"
            "cd ~/.agenticEvolve\n"
            "nohup python3 -m gateway.run > /dev/null 2>&1 &\n"
        )
        restart_sh.chmod(0o755)
        sp.Popen(
            [str(restart_sh)],
            start_new_session=True,
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )

    # ── /speak — text-to-speech ───────────────────────────────────

    async def _handle_speak(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Convert text to speech and send as Telegram voice message.

        Usage:
            /speak <text>           — convert text to voice (default voice)
            /speak --voice <name>   — use a specific edge-tts voice
            /speak --voices         — list available English voices
            /speak --mode <mode>    — set auto-TTS mode (off/always/inbound)
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []

        # /speak --voices — list voices
        if raw_args and raw_args[0] in ("--voices", "--list"):
            lang = raw_args[1] if len(raw_args) > 1 else "en"
            voices = await list_voices(lang)
            if not voices:
                await update.message.reply_text("No voices found.")
                return
            lines = [f"Edge TTS voices ({lang}):\n"]
            for v in voices[:30]:
                name = v.get("ShortName", "?")
                gender = v.get("Gender", "?")
                lines.append(f"  {name} ({gender})")
            if len(voices) > 30:
                lines.append(f"\n... and {len(voices) - 30} more")
            await update.message.reply_text("\n".join(lines))
            return

        # /speak --mode <off|always|inbound>
        if raw_args and raw_args[0] == "--mode":
            if len(raw_args) < 2:
                tts_cfg = get_tts_config(self._gateway.config if self._gateway else {})
                await update.message.reply_text(
                    f"Current TTS mode: {tts_cfg['mode']}\n"
                    f"Voice: {tts_cfg['voice']}\n\n"
                    "Modes:\n"
                    "  off — only /speak\n"
                    "  always — every reply gets voice\n"
                    "  inbound — reply with voice when you send voice"
                )
                return
            new_mode = raw_args[1].lower()
            if not TtsMode.is_valid(new_mode):
                await update.message.reply_text(f"Invalid mode: {new_mode}. Use: off, always, inbound")
                return
            # Update config in memory (hot-reload will persist on next config write)
            if self._gateway:
                if "tts" not in self._gateway.config:
                    self._gateway.config["tts"] = {}
                self._gateway.config["tts"]["mode"] = new_mode
            await update.message.reply_text(f"TTS mode set to: {new_mode}")
            return

        # Parse --voice flag
        flags = self._parse_flags(raw_args, {"--voice": {"type": "value"}})
        voice = flags.get("--voice") or None
        text = " ".join(raw_args)

        # If replying to a message, use that text
        if not text:
            reply_text, _ = self._get_reply_context(update)
            if reply_text:
                text = reply_text

        if not text:
            await update.message.reply_text(
                "*Usage:* `/speak <text>`\n\n"
                "*Options:*\n"
                "`--voice <name>` — use specific voice\n"
                "`--voices [lang]` — list voices\n"
                "`--mode <off|always|inbound>` — auto-TTS mode\n\n"
                "*Examples:*\n"
                "`/speak Hello, how are you today?`\n"
                "`/speak --voice en-US-GuyNeural Hey there!`\n"
                "`/speak --voices zh`\n\n"
                "Or reply to any message with `/speak` to voice it.",
                parse_mode="Markdown"
            )
            return

        # Get voice from config if not specified
        if not voice and self._gateway:
            tts_cfg = get_tts_config(self._gateway.config)
            voice = tts_cfg["voice"]

        await update.message.chat.send_action("record_voice")

        audio_path = await text_to_speech(text, voice=voice or "en-US-AndrewMultilingualNeural")

        if audio_path and audio_path.exists():
            try:
                with open(audio_path, "rb") as audio_file:
                    await update.message.reply_voice(
                        voice=audio_file,
                        caption=text[:200] if len(text) > 50 else None,
                    )
            except Exception as e:
                log.error(f"Failed to send voice: {e}")
                await update.message.reply_text(f"Failed to send voice message: {e}")
            finally:
                audio_path.unlink(missing_ok=True)
        else:
            await update.message.reply_text("TTS failed. Check logs.")

    # ── Voice/audio message handler ────────────────────────────────

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming voice messages — transcribe and process as text.

        Adapted from openclaw's audio-preflight + STT pipeline:
        1. Download voice/audio from Telegram
        2. Transcribe via Groq/OpenAI whisper
        3. Process transcript as regular message (with auto-TTS if mode=inbound)
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        # Get the voice or audio object
        voice = update.message.voice
        audio = update.message.audio
        media = voice or audio

        if not media:
            return

        duration = getattr(media, "duration", 0)
        file_size = getattr(media, "file_size", 0)

        # Download the audio file
        audio_dir = EXODIR / "tmp" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ext = ".ogg" if voice else ".mp3"
        audio_path = audio_dir / f"voice_{timestamp}_{media.file_id[:8]}{ext}"

        try:
            file = await context.bot.get_file(media.file_id)
            await file.download_to_drive(str(audio_path))
            log.info(f"Voice downloaded: {audio_path} ({file_size} bytes, {duration}s)")
        except Exception as e:
            log.error(f"Failed to download voice: {e}")
            await update.message.reply_text(f"Failed to download voice message: {e}")
            return

        # Transcribe
        await update.message.chat.send_action("typing")
        transcript = await speech_to_text(audio_path)

        if not transcript:
            await update.message.reply_text(
                "Could not transcribe voice message.\n"
                "Set GROQ_API_KEY (free) or OPENAI_API_KEY in .env for speech-to-text."
            )
            audio_path.unlink(missing_ok=True)
            return

        # Show transcript
        await update.message.reply_text(f"[Transcript]: {transcript}")

        # Process as regular message
        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)

        # Prepend voice context so Claude knows this is a transcribed voice message
        full_text = f"[The user sent a voice message. This is the transcript — treat it as if the user typed it directly]: {transcript}"
        reply_text, reply_urls = self._get_reply_context(update)
        if reply_text:
            full_text = f"[Replying to previous message: {reply_text[:1500]}]\n\n{transcript}"

        # Check for URLs — offer absorb/learn
        urls = self._extract_urls(full_text)
        if urls:
            non_url_text = full_text
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                await self._offer_absorb_learn(update, urls[0], "link in voice")
                audio_path.unlink(missing_ok=True)
                return

        # Regular chat with Claude
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
            response = await self.on_message("telegram", chat_id, user_id, full_text)
            if response:
                # Check TTS auto-mode — if inbound, reply with voice too
                config = self._gateway.config if self._gateway else {}
                audio_reply, clean_response = await maybe_tts_reply(response, config, inbound_was_voice=True)

                if audio_reply and audio_reply.exists():
                    try:
                        # Send text first (with directives stripped), then voice
                        for i in range(0, len(clean_response), 4000):
                            await update.message.reply_text(clean_response[i:i+4000])
                        with open(audio_reply, "rb") as af:
                            await update.message.reply_voice(voice=af)
                    except Exception as e:
                        log.warning(f"Failed to send TTS reply: {e}")
                    finally:
                        audio_reply.unlink(missing_ok=True)
                else:
                    for i in range(0, len(clean_response), 4000):
                        await update.message.reply_text(clean_response[i:i+4000])
        except Exception as e:
            log.error(f"Voice processing error: {e}")
            await update.message.reply_text(f"Error: {e}")
        finally:
            typing_active = False
            typing_task.cancel()
            audio_path.unlink(missing_ok=True)

    # ── /digest — morning briefing ──────────────────────────────────

    async def _handle_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a morning briefing: top signals, skills built, sessions, cost.

        Usage: /digest [--days N]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--days": {"type": "value", "cast": int, "default": 1},
        })
        days = max(1, min(flags["--days"], 7))

        chat_id = str(update.message.chat_id)
        await update.message.reply_text(f"Building digest (last {days}d)...")
        await self._send_digest(chat_id, days=days)

    async def _send_digest(self, chat_id: str, days: int = 1):
        """Build and send the digest message. Called by command or cron."""
        import sqlite3
        from ..agent import get_today_cost
        from ..session_db import DB_PATH

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        since_str = since.isoformat()

        # ── Sessions since cutoff ──
        sessions_summary = ""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT title, message_count, source, started_at FROM sessions "
                "WHERE started_at >= ? ORDER BY started_at DESC LIMIT 20",
                (since_str,)
            ).fetchall()
            conn.close()
            if rows:
                lines = []
                for r in rows:
                    title = (r["title"] or "(untitled)")[:50]
                    msgs = r["message_count"]
                    ts = r["started_at"][:16]
                    lines.append(f"  {ts} — {title} ({msgs} msgs)")
                sessions_summary = "\n".join(lines)
            else:
                sessions_summary = "  (none)"
        except Exception:
            sessions_summary = "  (error reading sessions)"

        # ── Top signals from today's signal dir ──
        signals_summary = ""
        try:
            today_str = now.strftime("%Y-%m-%d")
            sig_dir = EXODIR / "signals" / today_str
            if not sig_dir.exists():
                # Fall back to most recent signal dir
                sig_dirs = sorted((EXODIR / "signals").glob("????-??-??")) if (EXODIR / "signals").exists() else []
                sig_dir = sig_dirs[-1] if sig_dirs else None

            if sig_dir and sig_dir.exists():
                import json as _json
                signal_lines = []
                for f in sorted(sig_dir.glob("*.json"))[:3]:
                    try:
                        content = f.read_text().strip()
                        for line in content.splitlines()[:5]:
                            if not line.strip():
                                continue
                            obj = _json.loads(line)
                            title = obj.get("title", obj.get("name", ""))[:60]
                            source = obj.get("source", f.stem)
                            if title:
                                signal_lines.append(f"  [{source}] {title}")
                    except Exception:
                        pass
                signals_summary = "\n".join(signal_lines[:5]) if signal_lines else "  (none today)"
            else:
                signals_summary = "  (no signal dir found)"
        except Exception:
            signals_summary = "  (error reading signals)"

        # ── Skills built since cutoff ──
        skills_built = ""
        try:
            skills_dir = Path.home() / ".claude" / "skills"
            if skills_dir.exists():
                new_skills = []
                for skill_path in skills_dir.glob("*/SKILL.md"):
                    mtime = datetime.fromtimestamp(skill_path.stat().st_mtime, tz=timezone.utc)
                    if mtime >= since:
                        new_skills.append(skill_path.parent.name)
                skills_built = "\n".join(f"  {s}" for s in new_skills) if new_skills else "  (none)"
            else:
                skills_built = "  (no skills dir)"
        except Exception:
            skills_built = "  (error)"

        # ── Cost ──
        cost_today = get_today_cost()

        # ── Cron job next runs ──
        cron_summary = ""
        try:
            import json as _json
            if CRON_JOBS_FILE.exists():
                jobs = _json.loads(CRON_JOBS_FILE.read_text())
                active = [j for j in jobs if not j.get("paused")]
                lines = []
                for j in active[:5]:
                    nxt = j.get("next_run_at", "?")[:16]
                    jid = j.get("id", "?")
                    lines.append(f"  {jid} → {nxt}")
                cron_summary = "\n".join(lines) if lines else "  (none active)"
            else:
                cron_summary = "  (no jobs)"
        except Exception:
            cron_summary = "  (error)"

        period = "today" if days == 1 else f"last {days}d"
        text = (
            f"*Morning digest — {now.strftime('%Y-%m-%d %H:%M')} UTC*\n\n"
            f"*Sessions ({period}):*\n{sessions_summary}\n\n"
            f"*Top signals (latest):*\n{signals_summary}\n\n"
            f"*Skills built ({period}):*\n{skills_built}\n\n"
            f"*Cost today:* ${cost_today:.2f}\n\n"
            f"*Cron (next runs):*\n{cron_summary}"
        )

        if self.app and self.app.bot:
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=text, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=text)

        # Retro: mandatory reflection after morning digest
        try:
            import asyncio as _asyncio
            from ..retro import run_retro
            loop = _asyncio.get_running_loop()
            retro_text, retro_cost = await loop.run_in_executor(
                None,
                lambda: run_retro("digest", text,
                                  on_progress=lambda m: None,
                                  model="claude-sonnet-4-6")
            )
            retro_msg = f"*Retro*\n{retro_text}\n\n(${retro_cost:.3f})"
            if self.app and self.app.bot:
                for i in range(0, len(retro_msg), 4000):
                    try:
                        await self.app.bot.send_message(
                            chat_id=int(chat_id), text=retro_msg[i:i + 4000],
                            parse_mode="Markdown"
                        )
                    except Exception:
                        await self.app.bot.send_message(
                            chat_id=int(chat_id), text=retro_msg[i:i + 4000]
                        )
            if retro_cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "digest-retro", retro_cost)
        except Exception as e:
            log.warning(f"Retro after /digest failed (non-fatal): {e}")

    # ── /produce — brainstorm business ideas from latest signals ──────

    async def _handle_produce(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aggregate all signal sources and brainstorm app/business ideas.

        Usage: /produce [--model X] [--ideas N]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--model": {"type": "value"},
            "--ideas": {"type": "value", "cast": int, "default": 5},
        })
        num_ideas = max(1, min(flags["--ideas"], 10))
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        lang_instruction = self._get_lang_instruction(user_id)
        await update.message.reply_text(
            f"Aggregating signals from all sources...\n"
            f"Brainstorming {num_ideas} business ideas.\n~2-4 min."
        )

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        start_reporter()
        try:
            result_text, cost = await loop.run_in_executor(
                None, lambda: self._build_produce(num_ideas, model, on_progress_sync, lang_instruction)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Generate error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Generate failed: {e}")
            return
        finally:
            stop_reporter()

        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_text = result_text + footer
        for i in range(0, len(full_text), 4000):
            chunk = full_text[i:i + 4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "produce", cost)

    def _build_produce(self, num_ideas: int, model: str,
                        on_progress: Callable, lang_instruction: str = "") -> tuple[str, float]:
        """Aggregate signals and brainstorm business ideas. Runs in executor thread."""
        import glob as _glob
        from datetime import datetime as _dt

        signals_dir = Path.home() / ".agenticEvolve" / "signals"
        today = _dt.now().strftime("%Y-%m-%d")
        today_dir = signals_dir / today

        # Collect all signal files from today
        all_signals = []
        source_counts = {}

        if today_dir.exists():
            for f in sorted(today_dir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, list):
                        signals = data
                    else:
                        signals = [data]

                    source_name = f.stem
                    source_counts[source_name] = len(signals)
                    all_signals.extend(signals)
                except Exception:
                    continue

        if not all_signals:
            # Try to collect fresh signals
            on_progress("No signals found for today. Run /evolve first to collect signals.")
            return "No signals found for today. Run `/evolve --dry-run` first to collect fresh data from all sources.", 0.0

        on_progress(f"Loaded {len(all_signals)} signals from {len(source_counts)} sources")

        # Build a condensed summary of all signals for the prompt
        # Group by source, take top items by engagement
        source_summaries = []
        for source_name, count in sorted(source_counts.items()):
            source_signals = [s for s in all_signals if s.get("id", "").startswith(source_name.split("-")[0]) or
                              source_name in str(s.get("metadata", {}).get("relevance_tags", []))]
            if not source_signals:
                # fallback: match by source field
                source_signals = [s for s in all_signals
                                  if s.get("source", "") == source_name.replace("-", "")
                                  or s.get("source", "") == source_name]

            # Sort by engagement
            source_signals.sort(
                key=lambda x: (x.get("metadata", {}).get("points", 0)
                               or x.get("metadata", {}).get("stars", 0)
                               or x.get("metadata", {}).get("likes", 0)
                               or x.get("metadata", {}).get("replies", 0)
                               or 0),
                reverse=True
            )

            items = []
            for s in source_signals[:8]:
                title = s.get("title", "")
                content = s.get("content", "")[:200]
                url = s.get("url", "")
                meta = s.get("metadata", {})
                engagement = meta.get("points", 0) or meta.get("stars", 0) or meta.get("likes", 0) or 0
                items.append(f"  - {title} ({engagement} pts) {url}\n    {content}")

            if items:
                source_summaries.append(f"### {source_name} ({count} signals)\n" + "\n".join(items))

        signals_text = "\n\n".join(source_summaries)

        # Truncate to avoid context overflow
        if len(signals_text) > 40000:
            signals_text = signals_text[:40000] + "\n\n... (truncated)"

        on_progress("Brainstorming ideas...")

        from ..agent import invoke_claude_streaming

        prompt = (
            f"You are Vincent's personal AI business strategist.\n\n"
            f"Vincent is a developer who builds AI agents, onchain infrastructure, and developer tools. "
            f"He's looking for actionable app/business ideas he can build quickly (days to weeks, not months) "
            f"and monetize.\n\n"
            f"Here are the latest signals from {len(source_counts)} sources "
            f"({len(all_signals)} total signals):\n\n"
            f"{signals_text}\n\n"
            f"Based on these trends, generate exactly {num_ideas} concrete business/app ideas.\n\n"
            f"For EACH idea, provide:\n\n"
            f"## Idea N: [Name]\n"
            f"**One-liner**: What it does in one sentence\n"
            f"**Why now**: What trend/signal makes this timely (cite specific signals)\n"
            f"**Target users**: Who pays for this\n"
            f"**Revenue model**: How it makes money (be specific — pricing, tiers)\n"
            f"**Tech stack**: What to build with (leverage Vincent's skills: TypeScript, Python, Claude API, Solana, React/Next.js)\n"
            f"**MVP scope**: What to build in week 1 to validate\n"
            f"**Competitive moat**: Why this is hard to copy\n"
            f"**Estimated effort**: Days/weeks to MVP\n"
            f"**Revenue potential**: Realistic monthly revenue at 6 months\n\n"
            f"Prioritize ideas that:\n"
            f"- Solve a real pain point visible in the signals\n"
            f"- Can be built solo by one developer\n"
            f"- Have a clear path to first $1000/month\n"
            f"- Leverage AI/LLM trends (Vincent's strength)\n"
            f"- Are NOT just another chatbot wrapper\n\n"
            f"Rank ideas by feasibility × market timing × revenue potential.\n"
            f"Be brutally honest about risks and challenges for each.\n"
            f"Use Markdown formatting."
            + lang_instruction
        )

        result = invoke_claude_streaming(
            prompt,
            on_progress=on_progress,
            model=model,
            session_context=f"[Generate: {num_ideas} ideas from {len(all_signals)} signals]"
        )

        text = result.get("text", "No ideas generated.")
        cost = result.get("cost", 0.0)

        sources_line = ", ".join(f"{k}({v})" for k, v in sorted(source_counts.items()))
        header = (
            f"*Business Ideas — based on {len(all_signals)} signals*\n"
            f"Sources: {sources_line}\n\n"
        )
        return header + text, cost

    # ── /wechat — WeChat group chat digest ────────────────────────────

    async def _handle_wechat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Summarize recent WeChat group chat messages with AI analysis.

        Usage: /wechat [--hours N] [--model X]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--hours": {"type": "value", "cast": int, "default": 24},
            "--model": {"type": "value"},
        })
        hours = max(1, min(flags["--hours"], 168))  # max 7 days
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        lang_instruction = self._get_lang_instruction(user_id)
        await update.message.reply_text(f"Reading WeChat groups (last {hours}h)...\n~1-2 min.")

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        start_reporter()
        try:
            summary, cost = await loop.run_in_executor(
                None, lambda: self._build_wechat_digest(hours, model, on_progress_sync, lang_instruction)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"WeChat digest error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"WeChat digest failed: {e}")
            return
        finally:
            stop_reporter()

        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_text = summary + footer
        for i in range(0, len(full_text), 4000):
            chunk = full_text[i:i + 4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "wechat-digest", cost)

        # Retro: mandatory reflection after WeChat digest
        try:
            from ..retro import run_retro
            retro_text, retro_cost = await loop.run_in_executor(
                None,
                lambda: run_retro("wechat", summary,
                                  on_progress=lambda m: None,
                                  model="claude-sonnet-4-6")
            )
            retro_msg = f"*Retro*\n{retro_text}\n\n(${retro_cost:.3f})"
            for i in range(0, len(retro_msg), 4000):
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=retro_msg[i:i + 4000],
                        parse_mode="Markdown"
                    )
                except Exception:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=retro_msg[i:i + 4000]
                    )
            if retro_cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "wechat-retro", retro_cost)
        except Exception as e:
            log.warning(f"Retro after /wechat failed (non-fatal): {e}")

    def _build_wechat_digest(self, hours: int, model: str,
                             on_progress: Callable, lang_instruction: str = "") -> tuple[str, float]:
        """Build WeChat group chat digest using Claude. Runs in executor thread."""
        from pathlib import Path as _Path
        import sys

        decrypted_dir = _Path.home() / ".agenticEvolve" / "tools" / "wechat-decrypt" / "decrypted"
        if not decrypted_dir.exists():
            return ("No decrypted WeChat data found.\n"
                    "Run the decrypt pipeline first:\n"
                    "  `cd ~/.agenticEvolve/tools/wechat-decrypt`\n"
                    "  `sudo ./find_keys && python3 decrypt_db.py`"), 0.0

        # Load messages via collector
        collectors_dir = str(_Path.home() / ".agenticEvolve" / "collectors")
        if collectors_dir not in sys.path:
            sys.path.insert(0, collectors_dir)

        try:
            # Import from the wechat module using its path
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "wechat_collector",
                str(_Path.home() / ".agenticEvolve" / "collectors" / "wechat.py")
            )
            wechat_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wechat_mod)
            signals = wechat_mod.extract_group_messages(decrypted_dir, hours=hours)
        except Exception as e:
            return f"Failed to read WeChat messages: {e}", 0.0

        if not signals:
            return f"No WeChat group messages in the last {hours} hours.", 0.0

        # Build conversation text
        chat_lines = []
        total_msgs = 0
        for s in signals:
            meta = s.get("metadata", {})
            chat_lines.append(f"## {meta.get('group_name', 'Unknown')} "
                              f"({meta.get('message_count', 0)} msgs, "
                              f"{meta.get('unique_senders', 0)} senders)")
            chat_lines.append(s.get("content", ""))
            chat_lines.append("")
            total_msgs += meta.get("message_count", 0)

        chat_text = "\n".join(chat_lines)

        # Truncate to avoid context overflow
        if len(chat_text) > 30000:
            chat_text = chat_text[:30000] + "\n\n... (truncated)"

        on_progress("Analyzing conversations...")

        from ..agent import invoke_claude_streaming

        prompt = (
            f"You are Vincent's personal AI assistant analyzing his WeChat group chats.\n\n"
            f"Here are the last {hours} hours of group conversations ({total_msgs} messages "
            f"across {len(signals)} groups):\n\n"
            f"{chat_text}\n\n"
            f"Create a concise, actionable digest. IMPORTANT: Summarize EACH GROUP SEPARATELY.\n\n"
            f"For EACH group, use this structure:\n\n"
            f"---\n"
            f"## [Group Name] (N messages, N senders)\n\n"
            f"**关键要点** (3-5 bullet points — the most important things from THIS group)\n\n"
            f"**提到的工具 & 仓库** (list with brief descriptions, include URLs if shared)\n\n"
            f"**技术洞察** (useful tips, patterns, debugging techniques)\n\n"
            f"**热议话题** (what people are talking about most in this group)\n\n"
            f"---\n\n"
            f"After all groups, add a final section:\n\n"
            f"## Vincent 的 Action Items\n"
            f"(Combined actionable items across ALL groups, prioritized)\n\n"
            f"Be concise. Skip small talk and irrelevant messages. Focus on signal, not noise.\n"
            f"Use Markdown formatting. ALWAYS respond in simplified Chinese (简体中文) since the messages are from Chinese group chats."
            + (lang_instruction if lang_instruction else "")
        )

        result = invoke_claude_streaming(
            prompt,
            on_progress=on_progress,
            model=model,
            session_context=f"[WeChat digest: {hours}h, {len(signals)} groups]"
        )

        text = result.get("text", "No analysis generated.")
        cost = result.get("cost", 0.0)

        header = f"*WeChat Digest — last {hours}h*\n{total_msgs} messages across {len(signals)} groups\n\n"
        return header + text, cost

    async def _send_wechat_digest(self, chat_id: str, hours: int = 24):
        """Send a WeChat digest to a specific chat. Called by cron."""
        model = self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet"

        def _noop(msg):
            pass

        summary, cost = self._build_wechat_digest(hours, model, _noop)

        if self.app and self.app.bot:
            for i in range(0, len(summary), 4000):
                chunk = summary[i:i + 4000]
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                    )
                except Exception:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

    # ── /reflect — weekly self-analysis ─────────────────────────────

    async def _handle_reflect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run a weekly self-analysis: patterns, avoidance, next actions.

        Usage: /reflect [--days N] [--model X]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--days": {"type": "value", "cast": int, "default": 7},
            "--model": {"type": "value"},
        })
        days = max(1, min(flags["--days"], 30))
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        await update.message.reply_text(
            f"Reflecting on the last {days} days...\n~2-4 min."
        )

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=days)).isoformat()

        reflect_prompt = (
            f"You are the REFLECT agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
            f"Run a {days}-day self-analysis. Do the following:\n\n"
            f"1. Query the SQLite DB at {EXODIR}/memory/sessions.db for sessions and messages "
            f"since {since}. Focus on:\n"
            f"   SELECT title, message_count, started_at FROM sessions WHERE started_at >= '{since}' "
            f"ORDER BY started_at DESC;\n"
            f"   SELECT role, content FROM messages WHERE timestamp >= '{since}' ORDER BY timestamp DESC LIMIT 100;\n\n"
            f"2. Check git log in ~/Desktop/projects/agenticEvolve for commits since {since[:10]}:\n"
            f"   git -C ~/Desktop/projects/agenticEvolve log --oneline --since={since[:10]}\n\n"
            f"3. List skills installed (ls ~/.claude/skills/) and when they were created.\n\n"
            f"4. Read ~/.agenticEvolve/memory/MEMORY.md and ~/.agenticEvolve/memory/USER.md.\n\n"
            f"5. Analyze and return:\n"
            f"   a) *Patterns I'm seeing* — what topics, tools, or workflows keep coming up?\n"
            f"   b) *What am I avoiding?* — what was deferred, blocked, or repeatedly postponed?\n"
            f"   c) *3 things to build next* — ranked by impact, based on patterns + gaps\n"
            f"   d) *System health* — any memory pressure, high cost, stale sessions, or skill bloat?\n\n"
            f"Return a concise, actionable report. No filler."
        )

        start_reporter()
        try:
            from ..agent import invoke_claude_streaming
            result = await loop.run_in_executor(
                None,
                lambda: invoke_claude_streaming(
                    reflect_prompt,
                    on_progress=on_progress_sync,
                    model=model,
                    session_context="[Reflect pipeline]",
                )
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Reflect error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Reflect failed: {e}")
            return
        finally:
            stop_reporter()

        response = result.get("text", "No output.")
        cost = result.get("cost", 0)
        tools_used = get_tool_count()

        header = f"*Reflect — last {days}d*\n({tools_used} steps, ${cost:.2f})\n\n"
        full = header + response
        for i in range(0, len(full), 4000):
            chunk = full[i:i+4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "reflect", cost)

    # ── /do — natural language command ─────────────────────────────

    async def _handle_do(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Parse natural language into a structured command, then execute it in background."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--preview": {"aliases": ["--dry-run"], "type": "bool"}})
        preview = flags["--preview"]
        text = " ".join(raw_args)

        # Resolve reply context — inject URLs if user said "this"/"that"/"it"
        reply_text, reply_urls = self._get_reply_context(update)
        text = self._resolve_reply_target(text, update)
        reply_context = reply_text

        if not text:
            await update.message.reply_text(
                "*Usage:* `/do <natural language instruction>`\n\n"
                "*Options:*\n"
                "`--preview` — show parsed command without running it\n\n"
                "*Examples:*\n"
                "`/do absorb this repo https://github.com/foo/bar and skip the security scan`\n"
                "`/do learn about htmx`\n"
                "`/do --preview study this repo https://github.com/vercel/ai`\n"
                "`/do search for memory management in past sessions`\n"
                "`/do show me the cost so far`\n"
                "`/do schedule absorb langchain every day at 9am`\n\n"
                "I'll parse your intent, show the mapped command, and run it.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text("Parsing intent...")

        intent = await self._parse_intent(text, reply_context=reply_context)
        if not intent:
            await update.message.reply_text(
                "Couldn't map that to a known command. Try rephrasing, or use a command directly.\n\n"
                "Send `/help` for available commands."
            )
            return

        cmd = intent["command"]
        confidence = intent.get("confidence", 0)

        if preview:
            await update.message.reply_text(
                f"*Preview (not executed):*\n`{cmd}` (confidence: {confidence:.0%})\n\n"
                f"Run `/do {text}` without --preview to execute.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(
            f"Parsed: `{cmd}` (confidence: {confidence:.0%})\nRunning..."
        )
        await self._run_command_background(update, context, cmd)

    # ── Intent parser (natural language → command) ─────────────────

    # Commands the intent parser knows about
    _COMMAND_SCHEMA = """Available commands:
/absorb <repo-url or topic> [--dry-run] [--model <name>] [--skip-security-scan]
  Absorb patterns from a repo/topic into our system.
/learn <repo-url or topic> [--dry-run] [--model <name>] [--skip-security-scan]
  Deep-dive a repo/tech, extract patterns, evaluate benefit.
/evolve [--dry-run] [--model <name>] [--skip-security-scan]
  Run the evolution pipeline (collect signals, build skills).
/search <query> [--limit <n>]
  Full-text search across past sessions.
/sessions [--limit <n>]
  List recent sessions.
/newsession [title]
  Start a fresh session, optionally with a title.
/memory
  View bounded memory.
/cost [--week]
  View cost usage. Add --week for weekly total.
/status
  System status.
/skills
  List installed skills.
/learnings [query] [--limit <n>]
  List or search stored learnings.
/model <name>
  Switch model (e.g. sonnet, opus, haiku).
/produce [--ideas N] [--model <name>]
  Brainstorm business/app ideas from all collected signals.
/wechat [--hours N] [--model <name>]
  Summarize recent WeChat group chat messages.
/digest [--days N]
  Morning briefing (sessions, signals, skills, cost).
/gc [--dry-run]
  Run garbage collection.
/loop <interval> <prompt> [--model <name>] [--max-runs <n>] [--start-now]
  Schedule a recurring command.
/loops
  List scheduled loops.
/unloop <id>
  Remove a scheduled loop.
/pause <id|--all>
  Pause a scheduled loop or all loops.
/unpause <id|--all>
  Unpause a scheduled loop or all loops.
/queue
  List skills pending approval.
/approve <name> [--force]
  Approve a queued skill.
/reject <name>
  Reject a queued skill.
/soul
  View SOUL.md personality.
/config
  View runtime config.
/heartbeat
  Check if gateway is alive.
/notify <duration> <message>
  Set a one-time reminder.
/help
  Show help.
"""

    async def _parse_intent(self, text: str, reply_context: str = "") -> dict | None:
        """Parse natural language into a structured command using a lightweight Claude call.

        Returns dict with {command, display} or None if no command matched.
        """
        import subprocess as sp

        reply_section = ""
        if reply_context:
            reply_section = (
                f"\nThe user is REPLYING to this previous message (use it to resolve 'this', 'that', 'it', etc.):\n"
                f"---\n{reply_context[:1500]}\n---\n\n"
            )

        prompt = (
            "You are a command parser. The user sent a natural language message to an AI agent system.\n"
            "Your job: determine if this message maps to one of the available commands below.\n\n"
            f"{self._COMMAND_SCHEMA}\n"
            f"{reply_section}"
            "Rules:\n"
            "- If the message clearly maps to a command, return the exact command string.\n"
            "- If the message is general chat/question NOT related to any command, return null.\n"
            "- Preserve URLs and arguments exactly as the user provided them.\n"
            "- If the user says 'this', 'that', 'it' and there is a replied-to message with a URL, use that URL as the target.\n"
            "- Map synonyms: 'study'/'research'/'dive into' → /learn, 'integrate'/'absorb'/'steal from' → /absorb, "
            "'scan'/'evolve'/'find new tools' → /evolve, 'find'/'search for' → /search\n"
            "- Map flags from natural language: 'skip security'/'no security scan'/'skip scan' → --skip-security-scan, "
            "'preview'/'just check'/'dry run' → --dry-run\n\n"
            "Return ONLY a JSON object, nothing else:\n"
            '{"command": "/absorb https://... --skip-security-scan", "confidence": 0.95}\n'
            'or\n'
            '{"command": null, "confidence": 0.0}\n\n'
            f"User message: {text}"
        )

        try:
            proc = sp.run(
                ["claude", "-p", "--model", "haiku", prompt],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return None

            output = proc.stdout.strip()
            # Extract JSON from response
            start = output.find("{")
            end = output.rfind("}") + 1
            if start < 0 or end <= start:
                return None

            parsed = json.loads(output[start:end])
            cmd = parsed.get("command")
            confidence = parsed.get("confidence", 0)

            if not cmd or confidence < 0.7:
                return None

            return {"command": cmd, "display": cmd, "confidence": confidence}

        except Exception as e:
            log.warning(f"Intent parse failed: {e}")
            return None

    async def _run_command_background(self, update: Update, context: ContextTypes.DEFAULT_TYPE, command_str: str):
        """Parse a command string and dispatch it to the appropriate handler as a background task
        with periodic progress reports."""

        chat_id = int(update.message.chat_id)

        # Parse command string into parts
        parts = command_str.strip().split()
        if not parts:
            return
        cmd_name = parts[0].lstrip("/")
        cmd_args = parts[1:]

        # Map command names to handlers
        handler_map = {
            "absorb": self._handle_absorb,
            "learn": self._handle_learn,
            "evolve": self._handle_evolve,
            "search": self._handle_search,
            "sessions": self._handle_sessions,
            "newsession": self._handle_newsession,
            "memory": self._handle_memory,
            "cost": self._handle_cost,
            "status": self._handle_status,
            "skills": self._handle_skills,
            "learnings": self._handle_learnings,
            "model": self._handle_model,
            "gc": self._handle_gc,
            "loop": self._handle_loop,
            "loops": self._handle_loops,
            "unloop": self._handle_unloop,
            "pause": self._handle_pause,
            "unpause": self._handle_unpause,
            "queue": self._handle_queue,
            "approve": self._handle_approve,
            "reject": self._handle_reject,
            "soul": self._handle_soul,
            "config": self._handle_config,
            "heartbeat": self._handle_heartbeat,
            "notify": self._handle_notify,
            "help": self._handle_help,
            "wechat": self._handle_wechat,
            "digest": self._handle_digest,
            "produce": self._handle_produce,
            "lang": self._handle_lang,
        }

        handler = handler_map.get(cmd_name)
        if not handler:
            await self.app.bot.send_message(chat_id=chat_id, text=f"Unknown command: /{cmd_name}")
            return

        # For long-running commands, run in background with 1-min progress reports
        long_running = {"absorb", "learn", "evolve", "gc", "wechat", "produce"}

        if cmd_name in long_running:
            # Inject args into context so the handler sees them
            context.args = cmd_args
            start_time = datetime.now(timezone.utc)
            done = False

            # Progress reporter — sends a heartbeat every 60s
            async def progress_reporter():
                minute = 1
                while not done:
                    await asyncio.sleep(60)
                    if done:
                        break
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    try:
                        await self.app.bot.send_message(
                            chat_id=chat_id,
                            text=f"[`{command_str}`] Still running... ({int(elapsed)}s elapsed, ~{minute} min)",
                        )
                    except Exception:
                        pass
                    minute += 1

            reporter = asyncio.create_task(progress_reporter())

            try:
                await handler(update, context)
            except Exception as e:
                log.error(f"Background command error: {e}")
                await self.app.bot.send_message(chat_id=chat_id, text=f"Command failed: {e}")
            finally:
                done = True
                reporter.cancel()

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[`{command_str}`] Completed in {int(elapsed)}s.",
                )
            except Exception:
                pass
        else:
            # Short commands — run directly
            context.args = cmd_args
            await handler(update, context)

    # ── Regular text messages ────────────────────────────────────

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        user_id = update.message.from_user.id
        if not self._is_allowed(user_id):
            return await self._deny(update)

        chat_id = str(update.message.chat_id)
        text = update.message.text

        # Prepend reply context so Claude knows what's being referenced.
        # Label it clearly so Claude understands it is the QUOTED prior message,
        # not the user's new request — this prevents "which project?" confusion.
        reply_text, reply_urls = self._get_reply_context(update)
        if reply_text:
            text = (
                f"[Context: the user is replying to this prior assistant message — "
                f"use it as reference, do NOT re-answer it]\n"
                f"{reply_text[:1500]}\n\n"
                f"[User's new message:]\n{text}"
            )

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

        # General chat via Claude (use /do for intent parsing)
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
                    chunk = response[i:i+4000]
                    try:
                        await update.message.reply_text(chunk, parse_mode="Markdown")
                    except Exception:
                        # Fallback: send without Markdown if parse fails (e.g. unbalanced fences)
                        await update.message.reply_text(chunk)

            # Send any screenshots captured by browser MCP during this turn
            if self._gateway:
                session_key = f"telegram:{chat_id}"
                images = self._gateway.pop_pending_images(session_key)
                for img_bytes in images:
                    try:
                        import io
                        await update.message.reply_photo(photo=io.BytesIO(img_bytes))
                    except Exception as img_err:
                        log.warning(f"Failed to send screenshot: {img_err}")
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
            "recall": self._handle_recall,
            "skills": self._handle_skills,
            "soul": self._handle_soul,
            "config": self._handle_config,
            "autonomy": self._handle_autonomy,
            "pause": self._handle_pause,
            "unpause": self._handle_unpause,
            "do": self._handle_do,
            "speak": self._handle_speak,
            "screenshot": self._handle_screenshot,
            "restart": self._handle_restart,
            "wechat": self._handle_wechat,
            "digest": self._handle_digest,
            "produce": self._handle_produce,
            "lang": self._handle_lang,
        }
        for cmd, handler in commands.items():
            self.app.add_handler(CommandHandler(cmd, handler))

        # Regular text messages
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        # Photo handler
        self.app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))

        # Document/file handler
        self.app.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))

        # Voice/audio handler
        self.app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self._handle_voice))

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
                BotCommand("recall", "Search ALL memory layers at once"),
                BotCommand("skills", "List installed skills"),
                BotCommand("soul", "View agent personality"),
                BotCommand("config", "View runtime config"),
                BotCommand("autonomy", "View/change autonomy level"),
                BotCommand("speak", "Text-to-speech voice message"),
                BotCommand("restart", "Restart the gateway remotely"),
                BotCommand("pause", "Pause a cron job"),
                BotCommand("unpause", "Resume a paused cron job"),
                BotCommand("produce", "Brainstorm business ideas from signals"),
                BotCommand("lang", "Set output language (e.g. /lang zh)"),
                BotCommand("wechat", "WeChat group chat digest"),
                BotCommand("digest", "Morning briefing"),
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
