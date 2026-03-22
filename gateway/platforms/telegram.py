"""Telegram platform adapter using python-telegram-bot.

Command handlers are organized into mixins in gateway/commands/:
  AdminMixin     — start, help, status, memory, sessions, cost, model, config, soul, autonomy, skills, learnings
  PipelineMixin  — evolve, learn, absorb, gc, security prescan, auto-sync
  SignalsMixin   — produce, wechat, digest, reflect
  CronMixin      — loop, loops, unloop, pause, unpause, heartbeat, notify
  ApprovalMixin  — queue, approve, reject
  SearchMixin    — search, recall
  MediaMixin     — speak, voice, photo, document, screenshot
  MiscMixin      — restart, do/intent-parsing, callback handler, URL extraction
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable
from .base import BasePlatformAdapter, CircuitBreaker, retry_with_backoff
from ..voice import text_to_speech, speech_to_text, list_voices, maybe_tts_reply, get_tts_config, TtsMode, parse_tts_directives, detect_language_voice
from ..commands import (
    AdminMixin, PipelineMixin, SignalsMixin, CronMixin,
    ApprovalMixin, SearchMixin, MediaMixin, MiscMixin,
)
from ..commands.subscribe import SubscribeMixin

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


class TelegramAdapter(
    AdminMixin, PipelineMixin, SignalsMixin, CronMixin,
    ApprovalMixin, SearchMixin, MediaMixin, MiscMixin,
    SubscribeMixin,
    BasePlatformAdapter,
):
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
        self._breaker = CircuitBreaker("telegram")

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
            """Build compact stage progress indicator with done/current/pending states."""
            if not stages:
                return ""
            current = state["stage"].lower()
            seen_lower = [s.lower() for s in state["stages_seen"]]
            # Determine the index of the current stage in the pipeline
            current_idx = -1
            for i, s in enumerate(stages):
                if s.lower() in current or current in s.lower():
                    current_idx = i
                    break
            parts = []
            for i, s in enumerate(stages):
                sl = s.lower()
                is_current = (sl in current or current in sl)
                is_done = any(sl in seen or seen in sl for seen in seen_lower) and not is_current
                if is_current:
                    parts.append(f"[{s.upper()}]")
                elif is_done or (current_idx > i):
                    parts.append(f"v{s}")  # v prefix = done
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

            async def _send_initial():
                """Send the first status message immediately so user sees feedback right away."""
                try:
                    msg = await self.app.bot.send_message(
                        chat_id=int(chat_id), text="starting..."
                    )
                    state["msg_id"] = msg.message_id
                except Exception:
                    pass

            asyncio.ensure_future(_send_initial())
            state["reporter_task"] = asyncio.ensure_future(_reporter_loop())

        def stop_reporter():
            state["done"] = True
            if state["reporter_task"]:
                state["reporter_task"].cancel()

        def get_tool_count():
            return state["tool_count"]

        return on_progress_sync, get_tool_count, start_reporter, stop_reporter

    # ── send_photo (platform-level, not a command handler) ───────

    async def send_photo(self, chat_id: str, image_bytes: bytes, caption: str = "") -> None:
        """Send an image to a Telegram chat."""
        if self.app and self.app.bot:
            import io
            await self.app.bot.send_photo(
                chat_id=int(chat_id),
                photo=io.BytesIO(image_bytes),
                caption=caption[:1024] if caption else "",
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
        # Skip social/media URLs — pass them straight to Claude as chat context
        _SOCIAL_HOSTS = (
            "youtube.com", "youtu.be",
            "x.com", "twitter.com",
            "instagram.com", "tiktok.com",
            "reddit.com", "facebook.com",
        )
        urls = self._extract_urls(text)
        if urls:
            # If the message is mostly just a URL (link share), offer absorb/learn
            non_url_text = text
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            first_url = urls[0]
            is_social = any(h in first_url for h in _SOCIAL_HOSTS)
            _BROWSE_INTENTS = ("go to", "open", "navigate", "screenshot", "browse", "check", "look at", "visit", "see the page", "let see")
            has_browse_intent = any(kw in non_url_text.lower() for kw in _BROWSE_INTENTS)
            if len(non_url_text) < 30 and not is_social and not has_browse_intent:
                # Message is primarily a dev/repo link — offer absorb/learn
                await self._offer_absorb_learn(update, first_url, "link")
                return
            # Social/media links or URLs with context → fall through to Claude chat

        # Detect repeated greetings — if user sent a greeting within the last 5 messages,
        # skip Claude and return a direct engagement hook instead of another flat ack.
        _GREETINGS = {"hi", "hey", "hello", "yo", "sup", "hiya", "howdy"}
        is_greeting = text.strip().lower() in _GREETINGS
        if is_greeting:
            try:
                import sqlite3 as _sqlite3
                _db_path = Path.home() / ".agenticEvolve" / "memory" / "sessions.db"
                if _db_path.exists():
                    with _sqlite3.connect(str(_db_path)) as _conn:
                        rows = _conn.execute(
                            "SELECT role, content FROM messages "
                            "ORDER BY timestamp DESC LIMIT 8"
                        ).fetchall()
                    prior_user_greetings = [
                        r for r in rows
                        if r[0] == "user"
                        and r[1].strip().lower() in _GREETINGS
                    ]
                    if prior_user_greetings:
                        import hashlib as _hl
                        _hooks = [
                            "What are you building today?",
                            "What's the problem you're trying to solve?",
                            "What's the next thing to ship?",
                            "Anything blocking you right now?",
                            "What did you ship last?",
                        ]
                        # Deterministic rotation based on message count so it cycles
                        _idx = len(prior_user_greetings) % len(_hooks)
                        await update.message.reply_text(_hooks[_idx])
                        return
            except Exception:
                pass  # fall through to Claude on any DB error

        # General chat via Claude — live progress + streaming text
        import asyncio as _asyncio
        import time as _time

        # Progress state — shows tool calls in a single editable message
        _progress_msg = [None]
        _progress_lines = []
        _progress_dirty = [False]
        _progress_done = [False]
        _last_progress_edit = [0.0]

        def _on_progress(text: str):
            """Called from executor thread when Claude uses a tool."""
            _progress_lines.append(text)
            _progress_dirty[0] = True

        async def _progress_updater():
            """Background task: edit progress message every 3s."""
            while not _progress_done[0]:
                await _asyncio.sleep(3)
                if _progress_done[0]:
                    break
                if not _progress_dirty[0]:
                    # Send typing indicator even when no new tools
                    try:
                        await self.app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                    except Exception:
                        pass
                    continue
                _progress_dirty[0] = False
                recent = _progress_lines[-8:]
                display = "\n".join(recent)
                try:
                    if _progress_msg[0] is None:
                        _progress_msg[0] = await self.app.bot.send_message(
                            chat_id=int(chat_id), text=display)
                    else:
                        await self.app.bot.edit_message_text(
                            chat_id=int(chat_id),
                            message_id=_progress_msg[0].message_id,
                            text=display)
                except Exception:
                    pass
                try:
                    await self.app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                except Exception:
                    pass

        _updater_task = _asyncio.ensure_future(_progress_updater())

        # Streaming state — text chunks arrive from executor thread
        _stream_text = []

        def _on_text_chunk(chunk_text: str):
            """Called from executor thread when Claude emits text."""
            _stream_text.append(chunk_text)

        try:
            response = await self.on_message(
                "telegram", chat_id, str(user_id), text,
                on_text_chunk=_on_text_chunk,
                on_progress=_on_progress)

            # Stop progress updater
            _progress_done[0] = True
            _updater_task.cancel()

            # Delete progress message (clean chat)
            if _progress_msg[0]:
                try:
                    await self.app.bot.delete_message(
                        chat_id=int(chat_id),
                        message_id=_progress_msg[0].message_id)
                except Exception:
                    pass

            if response:
                # Send final response
                try:
                    await update.message.reply_text(response[:4000], parse_mode="Markdown")
                except Exception:
                    try:
                        await update.message.reply_text(response[:4000])
                    except Exception:
                        pass

                # If response > 4000 chars, send remaining chunks
                if len(response) > 4000:
                    for i in range(4000, len(response), 4000):
                        chunk = response[i:i+4000]
                        try:
                            await update.message.reply_text(chunk, parse_mode="Markdown")
                        except Exception:
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
            _progress_done[0] = True
            _updater_task.cancel()
            log.error(f"Telegram handler error: {e}")
            try:
                await update.message.reply_text(f"Error: {e}")
            except Exception:
                pass

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
            "decompose": self._handle_decompose,
            "loop": self._handle_loop,
            "loops": self._handle_loops,
            "unloop": self._handle_unloop,
            "heartbeat": self._handle_heartbeat,
            "notify": self._handle_notify,
            "queue": self._handle_queue,
            "approve": self._handle_approve,
            "reject": self._handle_reject,
            "scanskills": self._handle_scan_skills,
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
            "discord": self._handle_discord,
            "whatsapp": self._handle_whatsapp,
            "digest": self._handle_digest,
            "produce": self._handle_produce,
            "lang": self._handle_lang,
            "reflect": self._handle_reflect,
            "subscribe": self._handle_subscribe,
            "serve": self._handle_serve,
            "link": self._handle_link,
            "whoami": self._handle_whoami,
            "tasks": self._handle_tasks,
            "cancel": self._handle_cancel_task,
            "hooks": self._handle_hooks,
            "reload": self._handle_reload,
            "allowlist": self._handle_allowlist,
            "doctor": self._handle_doctor,
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

        mode = self.config.get("mode", "polling").lower()
        if mode == "webhook":
            wh = self.config.get("webhook", {})
            webhook_url = wh.get("url", "")
            if not webhook_url:
                log.error("Telegram webhook mode requires webhook.url in config")
                return
            port = int(wh.get("port", 8443))
            cert = wh.get("cert", "") or None
            key = wh.get("key", "") or None
            await self.app.updater.start_webhook(
                listen="0.0.0.0",
                port=port,
                url_path="/telegram",
                webhook_url=webhook_url + "/telegram",
                cert=cert,
                key=key,
            )
            log.info(f"Telegram webhook listening on 0.0.0.0:{port}")
        else:
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
                BotCommand("doctor", "System health check"),
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
        if not self.app or not self.app.bot:
            return
        for i in range(0, len(text), 4000):
            chunk = text[i:i+4000]
            if self._breaker.is_open():
                log.warning(f"[telegram] circuit breaker open, dropping send to {chat_id}")
                return
            try:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)
                self._breaker.record_success()
            except Exception as exc:
                self._breaker.record_failure()
                log.error(f"[telegram] send failed (chat={chat_id}): {exc}")
