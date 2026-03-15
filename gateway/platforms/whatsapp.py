"""WhatsApp platform adapter using Baileys Node.js bridge."""
import asyncio
import json
import logging
import subprocess
import os
from pathlib import Path
from .base import BasePlatformAdapter

log = logging.getLogger("agenticEvolve.whatsapp")

BRIDGE_DIR = Path.home() / ".agenticEvolve" / "whatsapp-bridge"


class WhatsAppAdapter(BasePlatformAdapter):
    name = "whatsapp"

    GROUP_PREFIXES = ("/ask", "/a", "@agent", "@bot")

    def __init__(self, config: dict, on_message):
        super().__init__(config, on_message)
        self.allowed_users = set(str(u) for u in config.get("allowed_users", []))
        self._serve_groups: set[str] = set()  # group JIDs being actively served
        self.process = None
        self._reader_task = None

    def _is_allowed(self, user_id: str) -> bool:
        # Deny-by-default (ZeroClaw pattern): empty allowlist = deny all
        if not self.allowed_users:
            return False
        return user_id in self.allowed_users

    async def start(self):
        bridge_js = BRIDGE_DIR / "bridge.js"
        if not bridge_js.exists():
            log.warning(f"WhatsApp bridge not found at {bridge_js}. Run 'ae setup whatsapp' first.")
            return

        # Check node_modules
        if not (BRIDGE_DIR / "node_modules").exists():
            log.info("Installing WhatsApp bridge dependencies...")
            proc = await asyncio.create_subprocess_exec(
                "npm", "install",
                cwd=str(BRIDGE_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()

        # Start the bridge as a subprocess
        self.process = await asyncio.create_subprocess_exec(
            "node", str(bridge_js),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BRIDGE_DIR)
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        log.info(f"WhatsApp bridge started (PID {self.process.pid})")

        # Load serve targets from DB
        try:
            from ..session_db import get_serve_targets
            targets = get_serve_targets("whatsapp")
            self._serve_groups = {t["target_id"] for t in targets if t["target_type"] == "group"}
            if self._serve_groups:
                log.info(f"WhatsApp serving {len(self._serve_groups)} groups from DB")
        except Exception as e:
            log.warning(f"Could not load serve targets: {e}")

    async def _read_loop(self):
        """Read JSON messages from the bridge stdout."""
        if not self.process or not self.process.stdout:
            return
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                line = line.decode().strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    log.debug(f"WhatsApp bridge non-JSON: {line}")
                    continue

                if msg.get("type") == "message":
                    chat_id = msg.get("chat_id", "")
                    user_id = msg.get("user_id", chat_id)
                    text = msg.get("text", "")

                    if not text:
                        continue

                    is_group = chat_id.endswith("@g.us")
                    is_served_group = is_group and chat_id in self._serve_groups

                    # For served groups: skip allowed_users + prefix check, respond to ALL messages
                    # For non-served groups: require allowed_users + prefix
                    # For DMs: require allowed_users only
                    if is_group:
                        if is_served_group:
                            # Strip prefix if present, but don't require it
                            for prefix in self.GROUP_PREFIXES:
                                if text.lower().startswith(prefix):
                                    text = text[len(prefix):].lstrip()
                                    break
                        else:
                            prefix_match = False
                            for prefix in self.GROUP_PREFIXES:
                                if text.lower().startswith(prefix):
                                    text = text[len(prefix):].lstrip()
                                    prefix_match = True
                                    break
                            if not prefix_match:
                                continue
                            if not text:
                                continue
                            if not self._is_allowed(user_id):
                                continue
                    else:
                        # DMs: require allowed_users
                        if not self._is_allowed(user_id):
                            continue

                    try:
                        response = await self.on_message("whatsapp", chat_id, user_id, text)
                        if response:
                            await self.send(chat_id, response)
                    except Exception as e:
                        log.error(f"WhatsApp handler error: {e}")

                elif msg.get("type") == "qr":
                    qr_data = msg.get("qr", "")
                    log.info("WhatsApp QR code received — generating image...")
                    # Generate QR image and save to tmp
                    try:
                        import qrcode
                        qr_img = qrcode.make(qr_data)
                        qr_path = Path("/tmp/whatsapp-qr.png")
                        qr_img.save(str(qr_path))
                        log.info(f"WhatsApp QR saved to {qr_path}")
                        # Try to send via Telegram if available
                        await self._notify_qr(qr_path)
                    except Exception as e:
                        log.warning(f"Could not generate QR image: {e}")
                        log.info(f"WhatsApp QR string: {qr_data}")

                elif msg.get("type") == "error":
                    log.error(f"WhatsApp bridge error: {msg.get('error', '')}")

                elif msg.get("type") == "ready":
                    log.info("WhatsApp connected")

                elif msg.get("type") in ("groups", "contacts"):
                    # Route response to pending _send_command future
                    resp_type = msg["type"]
                    if hasattr(self, "_pending_responses") and resp_type in self._pending_responses:
                        fut = self._pending_responses.pop(resp_type)
                        if not fut.done():
                            fut.set_result(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"WhatsApp read loop error: {e}")
                await asyncio.sleep(1)

    async def _notify_qr(self, qr_path: Path):
        """Send QR code image to Telegram for easy scanning."""
        try:
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
            if not bot_token or not chat_id:
                log.info("Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env to receive QR via Telegram")
                return
            import aiohttp
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            async with aiohttp.ClientSession() as session:
                with open(qr_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field("chat_id", chat_id)
                    data.add_field("caption", "Scan this QR code with WhatsApp to link your account.\n\nWhatsApp → Settings → Linked Devices → Link a Device")
                    data.add_field("photo", f, filename="whatsapp-qr.png")
                    async with session.post(url, data=data) as resp:
                        if resp.status == 200:
                            log.info("WhatsApp QR sent to Telegram")
                        else:
                            log.warning(f"Failed to send QR to Telegram: {resp.status}")
        except ImportError:
            log.info("Install aiohttp to send QR via Telegram: pip install aiohttp")
        except Exception as e:
            log.warning(f"Could not send QR to Telegram: {e}")

    async def stop(self):
        if self._reader_task:
            self._reader_task.cancel()
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
            log.info("WhatsApp bridge stopped")

    async def send(self, chat_id: str, text: str):
        if self.process and self.process.stdin:
            msg = json.dumps({"type": "send", "chat_id": chat_id, "text": text}) + "\n"
            self.process.stdin.write(msg.encode())
            await self.process.stdin.drain()

    async def _send_command(self, cmd: dict) -> dict | None:
        """Send a command to bridge.js and wait for a response of the expected type."""
        if not self.process or not self.process.stdin:
            return None
        self.process.stdin.write((json.dumps(cmd) + "\n").encode())
        await self.process.stdin.drain()
        # Wait for response (bridge emits it on stdout, read_loop stores it)
        # We use a simple future pattern
        if not hasattr(self, "_pending_responses"):
            self._pending_responses: dict[str, asyncio.Future] = {}
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        resp_type = cmd["type"].replace("list_", "")  # list_groups -> groups
        self._pending_responses[resp_type] = fut
        try:
            return await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            self._pending_responses.pop(resp_type, None)
            return None

    async def list_groups(self) -> list[dict]:
        """Get all WhatsApp groups via bridge.js."""
        resp = await self._send_command({"type": "list_groups"})
        groups = resp.get("groups", []) if resp else []
        log.info(f"list_groups returned {len(groups)} groups")
        return groups

    async def list_contacts(self) -> list[dict]:
        """Get recent WhatsApp contacts via bridge.js."""
        resp = await self._send_command({"type": "list_contacts"})
        contacts = resp.get("contacts", []) if resp else []
        log.info(f"list_contacts returned {len(contacts)} contacts")
        return contacts
