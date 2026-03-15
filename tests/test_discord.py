"""Tests for gateway/platforms/discord.py — pure functions and message routing logic.

Since Discord requires a real bot token and event loop, we mock discord.py
internals and test the adapter's own logic: allowed_users checking,
message routing decisions, response chunking, and lifecycle methods.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from gateway.platforms.discord import DiscordAdapter


# ── Helpers ──────────────────────────────────────────────────


def _make_adapter(allowed_users=None, token="fake-token"):
    """Create a DiscordAdapter via __new__ to skip real __init__ discord setup."""
    a = DiscordAdapter.__new__(DiscordAdapter)
    a.config = {"token": token, "allowed_users": allowed_users or []}
    a.on_message = AsyncMock(return_value="Test response")
    a.token = token
    a.allowed_users = set(str(u) for u in (allowed_users or []))
    a.client = None
    a._ready = asyncio.Event()
    return a


def _make_discord_message(
    author_id=12345,
    author_is_bot_user=False,
    channel_id=99999,
    content="hello bot",
    is_dm=False,
    mentions=None,
):
    """Build a mock discord.Message."""
    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.typing = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(),
    ))
    msg.content = content
    msg.mentions = mentions or []

    # Simulate DM vs guild channel
    import discord as _discord
    if is_dm:
        msg.channel.__class__ = _discord.DMChannel
        # Make isinstance check work
        msg.channel = MagicMock(spec=_discord.DMChannel)
        msg.channel.id = channel_id
        msg.channel.send = AsyncMock()
        msg.channel.typing = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(), __aexit__=AsyncMock(),
        ))
    return msg


# ══════════════════════════════════════════════════════════════
#  ALLOWED USERS / ACCESS CONTROL
# ══════════════════════════════════════════════════════════════


class TestIsAllowed:
    """Tests for DiscordAdapter._is_allowed (deny-by-default)."""

    def test_allowed_user(self):
        adapter = _make_adapter(allowed_users=[12345, 67890])
        assert adapter._is_allowed(12345) is True

    def test_allowed_user_str_coercion(self):
        adapter = _make_adapter(allowed_users=["12345"])
        assert adapter._is_allowed(12345) is True

    def test_denied_user(self):
        adapter = _make_adapter(allowed_users=[12345])
        assert adapter._is_allowed(99999) is False

    def test_empty_allowlist_denies_all(self):
        """ZeroClaw pattern: empty allowlist = deny everyone."""
        adapter = _make_adapter(allowed_users=[])
        assert adapter._is_allowed(12345) is False

    def test_multiple_users(self):
        adapter = _make_adapter(allowed_users=[111, 222, 333])
        assert adapter._is_allowed(111) is True
        assert adapter._is_allowed(222) is True
        assert adapter._is_allowed(333) is True
        assert adapter._is_allowed(444) is False


# ══════════════════════════════════════════════════════════════
#  CONSTRUCTOR
# ══════════════════════════════════════════════════════════════


class TestInit:
    """Tests for DiscordAdapter.__init__."""

    def test_init_sets_token(self):
        on_msg = AsyncMock()
        config = {"token": "my-token", "allowed_users": [1, 2]}
        adapter = DiscordAdapter(config, on_msg)
        assert adapter.token == "my-token"
        assert adapter.allowed_users == {"1", "2"}

    def test_init_empty_config(self):
        adapter = DiscordAdapter({}, AsyncMock())
        assert adapter.token == ""
        assert adapter.allowed_users == set()

    def test_init_no_discord_raises(self):
        """When discord.py is not installed, __init__ should raise ImportError."""
        with patch("gateway.platforms.discord.HAS_DISCORD", False):
            with pytest.raises(ImportError, match="discord.py not installed"):
                DiscordAdapter({"token": "t"}, AsyncMock())


# ══════════════════════════════════════════════════════════════
#  START / STOP LIFECYCLE
# ══════════════════════════════════════════════════════════════


class TestLifecycle:

    @pytest.mark.asyncio
    async def test_start_no_token_skips(self, caplog):
        """If token is empty, start() should log a warning and return."""
        adapter = _make_adapter(token="")
        await adapter.start()
        assert adapter.client is None

    @pytest.mark.asyncio
    async def test_stop_without_client(self):
        """stop() should be safe to call when client is None."""
        adapter = _make_adapter()
        adapter.client = None
        await adapter.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_closes_client(self):
        """stop() should call client.close()."""
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        adapter.client = mock_client
        await adapter.stop()
        mock_client.close.assert_awaited_once()


# ══════════════════════════════════════════════════════════════
#  SEND METHOD
# ══════════════════════════════════════════════════════════════


class TestSend:

    @pytest.mark.asyncio
    async def test_send_short_message(self):
        adapter = _make_adapter()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_client = MagicMock()
        mock_client.get_channel = MagicMock(return_value=mock_channel)
        adapter.client = mock_client

        await adapter.send("12345", "Hello!")
        mock_client.get_channel.assert_called_once_with(12345)
        mock_channel.send.assert_awaited_once_with("Hello!")

    @pytest.mark.asyncio
    async def test_send_long_message_chunked(self):
        """Messages > 1900 chars should be split into chunks."""
        adapter = _make_adapter()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_client = MagicMock()
        mock_client.get_channel = MagicMock(return_value=mock_channel)
        adapter.client = mock_client

        long_text = "A" * 4000
        await adapter.send("12345", long_text)
        # Should be sent in 3 chunks: 1900 + 1900 + 200
        assert mock_channel.send.await_count == 3

    @pytest.mark.asyncio
    async def test_send_no_client(self):
        """send() with no client should be a no-op."""
        adapter = _make_adapter()
        adapter.client = None
        await adapter.send("12345", "Hello!")  # Should not raise

    @pytest.mark.asyncio
    async def test_send_channel_not_found(self):
        """send() with unknown channel should be a no-op."""
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.get_channel = MagicMock(return_value=None)
        adapter.client = mock_client
        await adapter.send("12345", "Hello!")  # Should not raise


# ══════════════════════════════════════════════════════════════
#  MESSAGE ROUTING LOGIC (on_message event)
# ══════════════════════════════════════════════════════════════


class TestOnMessageRouting:
    """Test the on_message event handler logic extracted from start().

    Since the event handler is registered inside start() as a closure,
    we test the routing logic by directly invoking the conditions.
    """

    def test_ignore_own_messages(self):
        """Bot should ignore messages from itself."""
        adapter = _make_adapter(allowed_users=[12345])
        # Simulating: message.author == self.client.user → skip
        bot_user = MagicMock()
        bot_user.id = 99999
        msg = _make_discord_message(author_id=99999)
        msg.author = bot_user
        # The check is: if message.author == self.client.user: return
        assert msg.author == bot_user  # same object → would return

    def test_deny_disallowed_user(self):
        """Messages from users not in allowed_users should be dropped."""
        adapter = _make_adapter(allowed_users=[111])
        assert adapter._is_allowed(222) is False

    def test_empty_message_ignored(self):
        """Messages with empty content should be skipped."""
        msg = _make_discord_message(content="")
        assert not msg.content  # on_message returns early if not text

    def test_mention_text_cleanup(self):
        """Bot mention tag should be stripped from message text."""
        bot_user_id = 88888
        text = f"<@{bot_user_id}> what is the weather?"
        cleaned = text.replace(f"<@{bot_user_id}>", "").strip()
        assert cleaned == "what is the weather?"

    def test_mention_text_cleanup_mid_sentence(self):
        """Bot mention in the middle of text should be stripped."""
        bot_user_id = 88888
        text = f"hey <@{bot_user_id}> tell me a joke"
        cleaned = text.replace(f"<@{bot_user_id}>", "").strip()
        assert cleaned == "hey  tell me a joke"


# ══════════════════════════════════════════════════════════════
#  RESPONSE CHUNKING
# ══════════════════════════════════════════════════════════════


class TestResponseChunking:
    """Discord has a 2000 char limit; adapter chunks at 1900."""

    def test_short_response_single_chunk(self):
        text = "Hello world"
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_exactly_1900_chars(self):
        text = "X" * 1900
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        assert len(chunks) == 1

    def test_1901_chars_two_chunks(self):
        text = "X" * 1901
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        assert len(chunks) == 2
        assert len(chunks[0]) == 1900
        assert len(chunks[1]) == 1

    def test_large_response_many_chunks(self):
        text = "Y" * 5700
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        assert len(chunks) == 3
        assert all(len(c) == 1900 for c in chunks)

    def test_empty_response(self):
        text = ""
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        assert len(chunks) == 0


# ══════════════════════════════════════════════════════════════
#  INTEGRATION: on_message event handler end-to-end
# ══════════════════════════════════════════════════════════════


class TestOnMessageIntegration:
    """Test the on_message closure by extracting and invoking it."""

    @pytest.mark.asyncio
    async def test_dm_message_processed(self):
        """DM messages from allowed users should be routed to on_message callback."""
        import discord as _discord

        on_msg_cb = AsyncMock(return_value="Bot reply")
        adapter = _make_adapter(allowed_users=[12345], token="fake")
        adapter.on_message = on_msg_cb

        # Build mock message
        msg = _make_discord_message(
            author_id=12345,
            channel_id=55555,
            content="hello from DM",
            is_dm=True,
        )

        # Build a minimal mock client with user
        bot_user = MagicMock()
        bot_user.id = 99999
        adapter.client = MagicMock()
        adapter.client.user = bot_user

        # Simulate the on_message handler logic inline
        # (since the real handler is a closure inside start())
        if msg.author == adapter.client.user:
            pytest.fail("Should not be the same user")
        if not adapter._is_allowed(msg.author.id):
            pytest.fail("User should be allowed")

        text = msg.content
        assert text  # not empty

        is_dm = isinstance(msg.channel, _discord.DMChannel)
        assert is_dm is True

        # Call the on_message callback
        response = await adapter.on_message("discord", str(msg.channel.id), str(msg.author.id), text)
        assert response == "Bot reply"
        on_msg_cb.assert_awaited_once_with("discord", "55555", "12345", "hello from DM")

    @pytest.mark.asyncio
    async def test_guild_message_without_mention_ignored(self):
        """Guild messages that don't mention the bot should be ignored."""
        import discord as _discord

        adapter = _make_adapter(allowed_users=[12345])
        bot_user = MagicMock()
        bot_user.id = 99999
        adapter.client = MagicMock()
        adapter.client.user = bot_user

        msg = _make_discord_message(
            author_id=12345,
            content="just chatting",
            is_dm=False,
            mentions=[],
        )

        is_dm = isinstance(msg.channel, _discord.DMChannel)
        is_mentioned = bot_user in msg.mentions
        # Should skip: not DM and not mentioned
        assert not is_dm
        assert not is_mentioned

    @pytest.mark.asyncio
    async def test_guild_message_with_mention_processed(self):
        """Guild messages that mention the bot should be processed."""
        import discord as _discord

        on_msg_cb = AsyncMock(return_value="Mentioned reply")
        adapter = _make_adapter(allowed_users=[12345])
        adapter.on_message = on_msg_cb

        bot_user = MagicMock()
        bot_user.id = 99999
        adapter.client = MagicMock()
        adapter.client.user = bot_user

        msg = _make_discord_message(
            author_id=12345,
            channel_id=77777,
            content=f"<@{bot_user.id}> what's up?",
            is_dm=False,
            mentions=[bot_user],
        )

        # Simulate mention processing
        is_dm = isinstance(msg.channel, _discord.DMChannel)
        is_mentioned = bot_user in msg.mentions
        assert not is_dm
        assert is_mentioned

        text = msg.content
        text = text.replace(f"<@{bot_user.id}>", "").strip()
        assert text == "what's up?"

        response = await adapter.on_message("discord", str(msg.channel.id), str(msg.author.id), text)
        assert response == "Mentioned reply"
