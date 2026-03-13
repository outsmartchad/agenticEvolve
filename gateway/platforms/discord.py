"""Discord platform adapter using discord.py."""
import asyncio
import logging
from .base import BasePlatformAdapter

log = logging.getLogger(__name__)

try:
    import discord
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False


class DiscordAdapter(BasePlatformAdapter):
    name = "discord"

    def __init__(self, config: dict, on_message):
        super().__init__(config, on_message)
        if not HAS_DISCORD:
            raise ImportError("discord.py not installed. Run: pip install discord.py")
        self.token = config.get("token", "")
        self.allowed_users = set(str(u) for u in config.get("allowed_users", []))
        self.client = None
        self._ready = asyncio.Event()

    def _is_allowed(self, user_id: int) -> bool:
        # Deny-by-default (ZeroClaw pattern): empty allowlist = deny all
        if not self.allowed_users:
            return False
        return str(user_id) in self.allowed_users

    async def start(self):
        if not self.token:
            log.warning("Discord token not set, skipping")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        adapter = self

        @self.client.event
        async def on_ready():
            log.info(f"Discord adapter started as {self.client.user}")
            adapter._ready.set()

        @self.client.event
        async def on_message(message: discord.Message):
            if message.author == self.client.user:
                return
            if not adapter._is_allowed(message.author.id):
                return

            chat_id = str(message.channel.id)
            user_id = str(message.author.id)
            text = message.content

            if not text:
                return

            # Check if bot is mentioned or in DM
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self.client.user in message.mentions if self.client.user else False
            if not is_dm and not is_mentioned:
                return

            # Remove mention from text
            if is_mentioned and self.client.user:
                text = text.replace(f"<@{self.client.user.id}>", "").strip()

            async with message.channel.typing():
                try:
                    response = await adapter.on_message("discord", chat_id, user_id, text)
                    if response:
                        # Discord 2000 char limit
                        for i in range(0, len(response), 1900):
                            chunk = response[i:i+1900]
                            await message.channel.send(chunk)
                except Exception as e:
                    log.error(f"Discord handler error: {e}")
                    await message.channel.send(f"Error: {e}")

        asyncio.create_task(self.client.start(self.token))
        # Wait for ready with timeout
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            log.error("Discord connection timed out")

    async def stop(self):
        if self.client:
            await self.client.close()
            log.info("Discord adapter stopped")

    async def send(self, chat_id: str, text: str):
        if self.client:
            channel = self.client.get_channel(int(chat_id))
            if channel:
                for i in range(0, len(text), 1900):
                    await channel.send(text[i:i+1900])
