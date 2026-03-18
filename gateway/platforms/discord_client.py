"""Discord platform adapter using the desktop client (CDP + REST API).

Hooks into the running Discord desktop app via Chrome DevTools Protocol to:
  1. Capture real-time MESSAGE_CREATE events from the gateway WebSocket
  2. Send messages via Discord REST API using the user's auth token

Requires: Discord desktop app launched with --remote-debugging-port=9224
"""
import asyncio
import json
import logging
import os
from typing import Optional

import aiohttp

from .base import BasePlatformAdapter

log = logging.getLogger("agenticEvolve.discord_client")

DISCORD_API = "https://discord.com/api/v9"
CDP_PORT = 9224


class DiscordClientAdapter(BasePlatformAdapter):
    name = "discord"

    def __init__(self, config: dict, on_message):
        super().__init__(config, on_message)
        self.allowed_users = set(str(u) for u in config.get("allowed_users", []))
        self.watch_channels = set(str(c) for c in config.get("watch_channels", []))
        self._serve_channels: set[str] = set()  # channels where agent responds to ALL users
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self._cdp_ws = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        # Track last seen message per channel for polling
        self._last_msg_id: dict[str, str] = {}

    def _is_allowed(self, user_id: str) -> bool:
        if not self.allowed_users:
            return False
        return user_id in self.allowed_users

    async def start(self):
        # ══════════════════════════════════════════════════════════════
        # FULLY DISABLED — account got limited, second warning received.
        # No CDP connections, no REST API calls, no token extraction.
        # Discord data is read ONLY from local Chromium disk cache
        # (tools/discord-local/read_cache.py) — zero network calls.
        # ══════════════════════════════════════════════════════════════
        log.info("Discord adapter DISABLED — local cache only, no network calls")

    async def _get_cdp_targets(self) -> list:
        async with self._session.get(f"http://localhost:{CDP_PORT}/json") as resp:
            return await resp.json()

    async def _extract_token(self, ws_url: str) -> Optional[str]:
        """Extract Discord auth token by intercepting API requests via CDP."""
        import websockets

        try:
            async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
                # Enable Network domain
                await ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
                await ws.recv()

                # Trigger an API call by navigating
                await ws.send(json.dumps({
                    "id": 2,
                    "method": "Page.navigate",
                    "params": {"url": "https://discord.com/channels/@me"}
                }))

                # Listen for requests with Authorization header
                deadline = asyncio.get_event_loop().time() + 15
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(msg)

                        if data.get("method") == "Network.requestWillBeSent":
                            params = data.get("params", {})
                            headers = params.get("request", {}).get("headers", {})
                            auth = headers.get("Authorization") or headers.get("authorization")
                            if auth and "discord.com/api" in params.get("request", {}).get("url", ""):
                                log.info("Discord token captured via CDP")
                                # Disable network monitoring
                                await ws.send(json.dumps({"id": 3, "method": "Network.disable"}))
                                return auth
                    except asyncio.TimeoutError:
                        continue

                log.warning("Could not capture Discord token within timeout")
                return None
        except Exception as e:
            log.error(f"CDP token extraction failed: {e}")
            return None

    async def _api_get(self, path: str) -> Optional[dict]:
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        try:
            async with self._session.get(f"{DISCORD_API}{path}", headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    retry = (await resp.json()).get("retry_after", 5)
                    log.warning(f"Discord rate limited, waiting {retry}s")
                    await asyncio.sleep(retry)
                    return await self._api_get(path)
                elif resp.status in (401, 403):
                    log.error(f"Discord API {path}: {resp.status} — auth failed, stopping poll")
                    self._auth_failed = True
                    return None
                else:
                    log.error(f"Discord API {path}: {resp.status}")
                    return None
        except Exception as e:
            log.error(f"Discord API error: {e}")
            return None

    async def _api_post(self, path: str, data: dict) -> Optional[dict]:
        headers = {"Authorization": self.token, "Content-Type": "application/json"}
        try:
            async with self._session.post(
                f"{DISCORD_API}{path}", headers=headers, json=data
            ) as resp:
                if resp.status in (200, 201, 204):
                    if resp.content_length and resp.content_length > 0:
                        return await resp.json()
                    return {}
                elif resp.status == 429:
                    retry = (await resp.json()).get("retry_after", 5)
                    log.warning(f"Discord rate limited, waiting {retry}s")
                    await asyncio.sleep(retry)
                    return await self._api_post(path, data)
                else:
                    body = await resp.text()
                    log.error(f"Discord API POST {path}: {resp.status} {body[:200]}")
                    return None
        except Exception as e:
            log.error(f"Discord API POST error: {e}")
            return None

    async def _poll_messages(self):
        """Poll watched channels for new messages via REST API."""
        # Initialize last seen message IDs
        for channel_id in self.watch_channels:
            msgs = await self._api_get(f"/channels/{channel_id}/messages?limit=1")
            if msgs and len(msgs) > 0:
                self._last_msg_id[channel_id] = msgs[0]["id"]

        while True:
            if getattr(self, "_auth_failed", False):
                log.error("Discord auth failed — stopping poll loop")
                return
            try:
                for channel_id in self.watch_channels:
                    if getattr(self, "_auth_failed", False):
                        log.error("Discord auth failed mid-poll — stopping")
                        return
                    after = self._last_msg_id.get(channel_id, "0")
                    msgs = await self._api_get(
                        f"/channels/{channel_id}/messages?after={after}&limit=50"
                    )
                    if not msgs:
                        continue

                    # Process messages oldest first
                    # For served channels: batch all new messages into one combined
                    # prompt to avoid double-replying
                    is_served = channel_id in self._serve_channels
                    pending = []  # (msg_obj, author_id, text) tuples

                    for msg in reversed(msgs):
                        self._last_msg_id[channel_id] = msg["id"]

                        # Skip own messages
                        author_id = msg.get("author", {}).get("id", "")
                        if author_id == self.user_id:
                            continue

                        # Served channels: accept ALL users (no allowed_users gate)
                        # Non-served channels: check allowed_users
                        if not is_served:
                            if not self._is_allowed(author_id):
                                continue

                        text = msg.get("content", "")
                        if not text:
                            continue

                        # Store messages from served channels for digests
                        if is_served:
                            try:
                                from ..session_db import store_platform_message
                                author_name = msg.get("author", {}).get("username", "?")
                                store_platform_message(
                                    "discord", channel_id, author_id, author_name, text,
                                    message_id=msg.get("id"),
                                )
                            except Exception as e:
                                log.debug(f"Failed to store Discord message: {e}")

                        pending.append((msg, author_id, text))

                    if not pending:
                        continue

                    if is_served and len(pending) > 1:
                        # Batch: combine into one message with author labels
                        lines = []
                        for msg, aid, text in pending:
                            username = msg.get("author", {}).get("username", "?")
                            lines.append(f"{username}: {text}")
                        combined = "\n".join(lines)
                        last_msg = pending[-1][0]
                        log.info(f"Discord batch ({len(pending)} msgs) in {channel_id}")

                        # Wrap served group messages with content sanitizer
                        from ..content_sanitizer import wrap_platform_message
                        combined = wrap_platform_message(combined, "discord", sender="batch", is_served=True)

                        try:
                            response = await self.on_message(
                                "discord", channel_id, pending[-1][1], combined
                            )
                            if response:
                                await self.send(channel_id, response, reply_to=last_msg["id"])
                        except Exception as e:
                            log.error(f"Discord handler error: {e}")
                    else:
                        # Single message or non-served: process individually
                        for msg, author_id, text in pending:
                            log.info(
                                f"Discord message from {msg['author'].get('username')} "
                                f"in {channel_id}: {text[:50]}"
                            )
                            # Wrap served channel messages with content sanitizer
                            invoke_text = text
                            if is_served:
                                from ..content_sanitizer import wrap_platform_message
                                sender_name = msg.get("author", {}).get("username", "?")
                                invoke_text = wrap_platform_message(text, "discord", sender=sender_name, is_served=True)
                            try:
                                response = await self.on_message(
                                    "discord", channel_id, author_id, invoke_text
                                )
                                if response:
                                    await self.send(channel_id, response, reply_to=msg["id"])
                            except Exception as e:
                                log.error(f"Discord handler error: {e}")

                await asyncio.sleep(2)  # Poll every 2 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Discord poll error: {e}")
                await asyncio.sleep(5)

    async def send(self, chat_id: str, text: str, reply_to: str = None):
        """Send a message to a Discord channel via REST API.

        DISABLED: Discord account got limited from CDP-based sending.
        Keeping method signature so callers don't crash, but it no-ops.
        """
        log.warning("Discord send() is DISABLED — account was limited. Dropping message to %s", chat_id)
        return

    async def list_guilds(self) -> list[dict]:
        """List all guilds (servers) the user is in."""
        guilds = await self._api_get("/users/@me/guilds")
        return [{"id": g["id"], "name": g["name"]} for g in (guilds or [])]

    async def list_channels(self, guild_id: str) -> list[dict]:
        """List text channels in a guild, grouped by category."""
        channels = await self._api_get(f"/guilds/{guild_id}/channels")
        if not channels:
            return []
        # Build category name map
        cat_names = {c["id"]: c["name"] for c in channels if c.get("type") == 4}
        # Text (0), announcement (5), forum (15), voice-text (13)
        text_channels = [
            {
                "id": c["id"], "name": c["name"], "type": c["type"],
                "category": cat_names.get(c.get("parent_id", ""), ""),
                "position": c.get("position", 999),
            }
            for c in channels
            if c.get("type") in (0, 5)
        ]
        text_channels.sort(key=lambda c: (c["category"], c["position"]))
        return text_channels

    async def list_dm_channels(self) -> list[dict]:
        """List DM channels."""
        channels = await self._api_get("/users/@me/channels")
        if not channels:
            return []
        result = []
        for c in channels:
            recipients = ", ".join(
                r.get("username", "?") for r in c.get("recipients", [])
            )
            result.append({
                "id": c["id"],
                "name": recipients or "Unknown",
                "type": "dm" if c.get("type") == 1 else "group_dm",
            })
        return result

    async def get_messages(self, channel_id: str, after: str = "0",
                           limit: int = 50) -> list[dict]:
        """Fetch messages from a channel (for digest)."""
        msgs = await self._api_get(
            f"/channels/{channel_id}/messages?after={after}&limit={limit}"
        )
        if not msgs:
            return []
        return [
            {
                "id": m["id"],
                "author": m.get("author", {}).get("username", "?"),
                "author_id": m.get("author", {}).get("id", ""),
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp", ""),
            }
            for m in reversed(msgs)  # oldest first
        ]

    async def stop(self):
        if self._poll_task:
            self._poll_task.cancel()
        if self._reader_task:
            self._reader_task.cancel()
        if self._session:
            await self._session.close()
        log.info("Discord client adapter stopped")
