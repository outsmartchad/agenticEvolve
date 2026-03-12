"""WhatsApp platform adapter using Baileys Node.js bridge."""
import asyncio
import json
import logging
import subprocess
import os
from pathlib import Path
from .base import BasePlatformAdapter

log = logging.getLogger(__name__)

BRIDGE_DIR = Path.home() / ".agenticEvolve" / "whatsapp-bridge"


class WhatsAppAdapter(BasePlatformAdapter):
    name = "whatsapp"

    def __init__(self, config: dict, on_message):
        super().__init__(config, on_message)
        self.allowed_users = set(str(u) for u in config.get("allowed_users", []))
        self.process = None
        self._reader_task = None

    def _is_allowed(self, user_id: str) -> bool:
        if not self.allowed_users:
            return True
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
        log.info("WhatsApp bridge started")

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

                    if not text or not self._is_allowed(user_id):
                        continue

                    try:
                        response = await self.on_message("whatsapp", chat_id, user_id, text)
                        if response:
                            await self.send(chat_id, response)
                    except Exception as e:
                        log.error(f"WhatsApp handler error: {e}")

                elif msg.get("type") == "qr":
                    log.info(f"WhatsApp QR code: {msg.get('qr', 'scan in terminal')}")

                elif msg.get("type") == "ready":
                    log.info("WhatsApp connected")

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"WhatsApp read loop error: {e}")
                await asyncio.sleep(1)

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
