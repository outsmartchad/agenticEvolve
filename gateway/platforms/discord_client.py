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
        self._session = aiohttp.ClientSession()

        # Step 1: Connect to Discord desktop app via CDP
        try:
            targets = await self._get_cdp_targets()
        except Exception as e:
            log.error(f"Cannot connect to Discord desktop app CDP on port {CDP_PORT}: {e}")
            log.info("Launch Discord with: open -a Discord --args --remote-debugging-port=9224")
            return

        page_target = next((t for t in targets if t.get("type") == "page"), None)
        if not page_target:
            log.error("No Discord page target found via CDP")
            return

        ws_url = page_target["webSocketDebuggerUrl"]
        log.info(f"Connecting to Discord CDP: {page_target.get('title', 'unknown')}")

        # Step 2: Extract auth token via CDP Network interception
        self.token = await self._extract_token(ws_url)
        if not self.token:
            # Try reading from file as fallback
            token_file = os.path.expanduser("~/.agenticEvolve/.discord-token")
            if os.path.exists(token_file):
                with open(token_file) as f:
                    self.token = f.read().strip()
                log.info("Using cached Discord token from .discord-token")

        if not self.token:
            log.error("Could not extract Discord token. Make sure you're logged in.")
            return

        # Save token for future use
        token_file = os.path.expanduser("~/.agenticEvolve/.discord-token")
        with open(token_file, "w") as f:
            f.write(self.token)

        # Step 3: Get current user info
        user = await self._api_get("/users/@me")
        if user:
            self.user_id = user.get("id")
            log.info(f"Discord client connected as {user.get('username')} (ID: {self.user_id})")

        # Step 4: Load serve targets from DB and merge into watch_channels
        try:
            from ..session_db import get_serve_targets
            targets = get_serve_targets("discord")
            for t in targets:
                tid = str(t["target_id"])
                self.watch_channels.add(tid)
                self._serve_channels.add(tid)
            if targets:
                log.info(f"Loaded {len(targets)} Discord serve targets from DB")
        except Exception as e:
            log.warning(f"Failed to load Discord serve targets: {e}")

        # Step 5: Start message polling
        # CDP WebSocket frame interception doesn't work for ETF+zstd,
        # so we poll the REST API for new messages in watched channels
        if self.watch_channels:
            self._poll_task = asyncio.create_task(self._poll_messages())
            log.info(f"Polling {len(self.watch_channels)} channels for new messages")
        else:
            log.warning("No watch_channels configured — Discord adapter won't receive messages")

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
            try:
                for channel_id in self.watch_channels:
                    after = self._last_msg_id.get(channel_id, "0")
                    msgs = await self._api_get(
                        f"/channels/{channel_id}/messages?after={after}&limit=50"
                    )
                    if not msgs:
                        continue

                    # Process messages oldest first
                    for msg in reversed(msgs):
                        self._last_msg_id[channel_id] = msg["id"]

                        # Skip own messages
                        author_id = msg.get("author", {}).get("id", "")
                        if author_id == self.user_id:
                            continue

                        # Served channels: accept ALL users (no allowed_users gate)
                        # Non-served channels: check allowed_users
                        if channel_id not in self._serve_channels:
                            if not self._is_allowed(author_id):
                                continue

                        text = msg.get("content", "")
                        if not text:
                            continue

                        # Store messages from served channels for digests
                        if channel_id in self._serve_channels:
                            try:
                                from ..session_db import store_platform_message
                                author_name = msg.get("author", {}).get("username", "?")
                                store_platform_message("discord", channel_id, author_id, author_name, text)
                            except Exception as e:
                                log.debug(f"Failed to store Discord message: {e}")

                        log.info(
                            f"Discord message from {msg['author'].get('username')} "
                            f"in {channel_id}: {text[:50]}"
                        )

                        try:
                            response = await self.on_message(
                                "discord", channel_id, author_id, text
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
        """Send a message to a Discord channel via REST API."""
        # Discord 2000 char limit
        for idx, i in enumerate(range(0, len(text), 1900)):
            chunk = text[i:i + 1900]
            payload = {"content": chunk}
            # Only reply to the original message on the first chunk
            if idx == 0 and reply_to:
                payload["message_reference"] = {"message_id": reply_to}
            await self._api_post(
                f"/channels/{chat_id}/messages",
                payload
            )

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
