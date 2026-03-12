"""Telegram platform adapter using python-telegram-bot."""
import asyncio
import logging
from .base import BasePlatformAdapter

log = logging.getLogger(__name__)

try:
    from telegram import Update
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

    def _is_allowed(self, user_id: int) -> bool:
        if not self.allowed_users:
            return True  # no allowlist = allow all
        return str(user_id) in self.allowed_users

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        user_id = update.message.from_user.id
        if not self._is_allowed(user_id):
            return

        chat_id = str(update.message.chat_id)
        text = update.message.text

        # Send typing indicator
        await update.message.chat.send_action("typing")

        # Process through agent
        try:
            response = await self.on_message("telegram", chat_id, str(user_id), text)
            if response:
                # Split long messages (Telegram 4096 char limit)
                for i in range(0, len(response), 4000):
                    chunk = response[i:i+4000]
                    await update.message.reply_text(chunk)
        except Exception as e:
            log.error(f"Telegram handler error: {e}")
            await update.message.reply_text(f"Error: {e}")

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        await update.message.reply_text(
            "agenticEvolve connected. Send me a message and I'll process it with Claude."
        )

    async def start(self):
        if not self.token:
            log.warning("Telegram token not set, skipping")
            return
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self._handle_start))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
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
