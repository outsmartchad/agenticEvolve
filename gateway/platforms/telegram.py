"""Telegram platform adapter using python-telegram-bot."""
import asyncio
import logging
import sys
from pathlib import Path
from .base import BasePlatformAdapter

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"

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
        # Will be set by GatewayRunner after creation
        self._gateway = None

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
        log.info(f"Unverified user attempted access: {user_id}")

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
            "/help — Show this help\n"
            "/status — System status\n"
            "/memory — Show bounded memory\n"
            "/sessions — Recent sessions\n"
            "/newsession — Force start a new session\n"
            "/cost — Today's cost\n"
            "/model — Show current model\n\n"
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

        # Memory sizes
        mem_path = EXODIR / "memory" / "MEMORY.md"
        user_path = EXODIR / "memory" / "USER.md"
        mem_chars = len(mem_path.read_text()) if mem_path.exists() else 0
        user_chars = len(user_path.read_text()) if user_path.exists() else 0

        text = (
            f"*agenticEvolve status*\n\n"
            f"Gateway: running\n"
            f"Memory: {mem_chars}/2200 chars\n"
            f"User profile: {user_chars}/1375 chars\n"
            f"Sessions: {s['total_sessions']} total, {s['total_messages']} messages\n"
            f"DB size: {s['db_size_mb']} MB\n"
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
            f"*MEMORY.md* ({len(mem)}/2200 chars)\n\n"
            f"{mem}\n\n"
            f"---\n\n"
            f"*USER.md* ({len(user)}/1375 chars)\n\n"
            f"{user}"
        )
        # Truncate if too long for Telegram
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
            await update.message.reply_text("No sessions yet.")
            return

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

        # Force-expire the current session via the gateway
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
        # Read config for cap
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
                    chunk = response[i:i+4000]
                    await update.message.reply_text(chunk)
        except Exception as e:
            log.error(f"Telegram handler error: {e}")
            await update.message.reply_text(f"Error: {e}")

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self):
        if not self.token:
            log.warning("Telegram token not set, skipping")
            return
        self.app = Application.builder().token(self.token).build()

        # Register command handlers
        self.app.add_handler(CommandHandler("start", self._handle_start))
        self.app.add_handler(CommandHandler("help", self._handle_help))
        self.app.add_handler(CommandHandler("status", self._handle_status))
        self.app.add_handler(CommandHandler("memory", self._handle_memory))
        self.app.add_handler(CommandHandler("sessions", self._handle_sessions))
        self.app.add_handler(CommandHandler("newsession", self._handle_newsession))
        self.app.add_handler(CommandHandler("cost", self._handle_cost))
        self.app.add_handler(CommandHandler("model", self._handle_model))

        # Regular messages (non-command text)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

        # Set bot commands menu
        try:
            await self.app.bot.set_my_commands([
                BotCommand("help", "Show available commands"),
                BotCommand("status", "System status"),
                BotCommand("memory", "Show bounded memory"),
                BotCommand("sessions", "Recent sessions"),
                BotCommand("newsession", "Start a new session"),
                BotCommand("cost", "Today's cost"),
                BotCommand("model", "Show current model"),
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
