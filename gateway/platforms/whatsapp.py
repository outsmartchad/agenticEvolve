"""WhatsApp platform adapter using Baileys Node.js bridge."""
import asyncio
import json
import logging
import subprocess
import os
from pathlib import Path
from .base import BasePlatformAdapter, CircuitBreaker, retry_with_backoff

log = logging.getLogger("agenticEvolve.whatsapp")

BRIDGE_DIR = Path.home() / ".agenticEvolve" / "whatsapp-bridge"


class WhatsAppAdapter(BasePlatformAdapter):
    name = "whatsapp"

    GROUP_PREFIXES = ("/ask", "/a", "@agent", "@bot")

    def __init__(self, config: dict, on_message):
        super().__init__(config, on_message)
        self.allowed_users = set(str(u) for u in config.get("allowed_users", []))
        self._serve_groups: set[str] = set()  # group JIDs being actively served
        self._serve_contacts: set[str] = set()  # contact JIDs being actively served
        self._subscribe_groups: set[str] = set()  # group JIDs subscribed for digests
        self._seen_msg_ids: set[str] = set()  # dedup: prevent processing same message multiple times
        self._seen_msg_ids_max = 2000  # cap to prevent unbounded growth
        # Message debouncing for served groups (OpenClaw pattern)
        from ..debounce import MessageDebouncer
        self._debouncer = MessageDebouncer(
            window_seconds=config.get("debounce_seconds", 2.5),
            max_wait=config.get("debounce_max_wait", 8.0),
        )
        self._seen_content: dict[str, float] = {}
        self._last_reply_ts: dict[str, float] = {}
        self._pending_responses: dict[str, asyncio.Future] = {}
        self.process = None
        self._reader_task = None
        self._breaker = CircuitBreaker("whatsapp", fail_threshold=5, recovery_secs=60)

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

        # Load serve + subscribe targets from DB
        try:
            from ..session_db import get_serve_targets, get_subscriptions
            targets = get_serve_targets("whatsapp")
            self._serve_groups = {t["target_id"] for t in targets if t["target_type"] == "group"}
            self._serve_contacts = {t["target_id"] for t in targets if t["target_type"] == "contact"}
            serve_total = len(self._serve_groups) + len(self._serve_contacts)
            if serve_total:
                log.info(f"WhatsApp serving {len(self._serve_groups)} groups + {len(self._serve_contacts)} contacts from DB")
            # Load subscribed groups (for message storage / digests)
            _wa_users = self.config.get("platforms", {}).get("whatsapp", {}).get("allowed_users", [])
            _wa_owner = str(_wa_users[0]).split("@")[0] if _wa_users else ""
            subs = get_subscriptions(_wa_owner, mode="subscribe", platform="whatsapp")
            self._subscribe_groups = {s["target_id"] for s in subs}
            if self._subscribe_groups:
                log.info(f"WhatsApp storing messages for {len(self._subscribe_groups)} subscribed groups")
        except Exception as e:
            log.warning(f"Could not load serve/subscribe targets: {e}")

    async def _read_loop(self):
        """Read JSON messages from the bridge stdout with exponential backoff on errors."""
        if not self.process or not self.process.stdout:
            return
        _error_count = 0
        _base_delay = 1.0
        _max_delay = 60.0
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                _error_count = 0  # reset backoff on successful read
                self._breaker.record_success()
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
                    image_path = msg.get("image_path")
                    file_path = msg.get("file_path")
                    file_name = msg.get("file_name", "")
                    audio_path = msg.get("audio_path")
                    sender_name = msg.get("sender_name", user_id.split("@")[0])

                    # Extract quoted/reply-to context
                    quoted_text = msg.get("quoted_text")
                    quoted_sender = msg.get("quoted_sender")

                    if audio_path:
                        log.info(f"WhatsApp audio received: {audio_path}")
                    if not text and not image_path and not file_path and not audio_path:
                        continue

                    # Dedup: Baileys can deliver the same message multiple times
                    # (history sync, retry, reconnect, multi-device).
                    # Layer 1: message ID dedup
                    # Layer 2: content+chat hash dedup (catches different IDs for same message)
                    msg_id = msg.get("message_id")
                    if msg_id:
                        if msg_id in self._seen_msg_ids:
                            log.debug(f"WhatsApp dedup (id): skipping {msg_id}")
                            continue
                        self._seen_msg_ids.add(msg_id)
                        if len(self._seen_msg_ids) > self._seen_msg_ids_max:
                            to_keep = list(self._seen_msg_ids)[-self._seen_msg_ids_max // 2:]
                            self._seen_msg_ids = set(to_keep)

                    # Content-based dedup: same chat + same text within 5s window
                    import hashlib as _hashlib
                    import time as _time2
                    _content_key = _hashlib.md5(f"{chat_id}:{user_id}:{text[:200]}".encode()).hexdigest()
                    _now2 = _time2.monotonic()
                    _last_seen = self._seen_content.get(_content_key, 0)
                    if _now2 - _last_seen < 5.0:
                        log.debug(f"WhatsApp dedup (content): skipping duplicate in {chat_id} ({_now2 - _last_seen:.1f}s)")
                        continue
                    self._seen_content[_content_key] = _now2
                    # Prune old entries every 100 messages
                    if len(self._seen_content) > 500:
                        cutoff = _now2 - 30.0
                        self._seen_content = {k: v for k, v in self._seen_content.items() if v > cutoff}

                    is_group = chat_id.endswith("@g.us")
                    is_served_group = is_group and chat_id in self._serve_groups
                    is_served_contact = (not is_group) and chat_id in self._serve_contacts
                    is_served = is_served_group or is_served_contact

                    # ── @agent trigger: works for ANYONE, in groups AND DMs ──
                    # Bypasses allowed_users check. This is the universal entry point.
                    _is_agent_invoke = False
                    _agent_prefix = "@agent"
                    if text.lower().startswith(_agent_prefix):
                        text = text[len(_agent_prefix):].lstrip()
                        _is_agent_invoke = True
                        # Prepend quoted message as context if replying
                        if quoted_text:
                            _quoted_by = f" (by {quoted_sender})" if quoted_sender else ""
                            text = (
                                f"[Replying to message{_quoted_by}: \"{quoted_text}\"]\n\n"
                                f"{text}" if text else
                                f"[Replying to message{_quoted_by}: \"{quoted_text}\"]\n\n"
                                "Analyze and respond to this message."
                            )
                        if not text:
                            continue  # @agent with no prompt and no reply

                    # Store messages from served + subscribed groups for digests
                    if is_group and (chat_id in self._serve_groups or chat_id in self._subscribe_groups):
                        try:
                            from ..session_db import store_platform_message
                            msg_id = msg.get("message_id")
                            store_platform_message(
                                "whatsapp", chat_id, user_id, sender_name, text,
                                message_id=msg_id
                            )
                        except Exception as e:
                            log.debug(f"Failed to store WhatsApp message: {e}")

                    # ── Access control ──
                    # @agent invocations: always allowed (anyone can use)
                    # Served groups: respond to ALL messages
                    # Non-served groups: require prefix + allowed_users
                    # DMs: require allowed_users (unless served contact)
                    if _is_agent_invoke:
                        pass  # always allowed
                    elif is_group:
                        if is_served_group:
                            # Strip prefix if present, but don't require it
                            for prefix in self.GROUP_PREFIXES:
                                if text.lower().startswith(prefix):
                                    text = text[len(prefix):].lstrip()
                                    break
                            # Prepend quoted context for served group messages too
                            if quoted_text and not text.startswith("[Replying"):
                                _quoted_by = f" (by {quoted_sender})" if quoted_sender else ""
                                text = f"[Replying to{_quoted_by}: \"{quoted_text}\"]\n\n{text}"
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
                        # DMs: served contacts skip allowed_users check
                        if not is_served_contact and not self._is_allowed(user_id):
                            continue

                    # Build message key for reply-to quoting
                    msg_key = None
                    if msg.get("message_id"):
                        msg_key = {
                            "remoteJid": chat_id,
                            "id": msg["message_id"],
                            "fromMe": False,
                        }
                        if is_group and user_id != chat_id:
                            msg_key["participant"] = user_id

                    # Self-reply cooldown: if we sent a response to this chat
                    # very recently, this is likely our own message echoed back.
                    import time as _time
                    _now = _time.monotonic()
                    _last = self._last_reply_ts.get(chat_id, 0)
                    if _now - _last < 3.0 and not _is_agent_invoke:
                        log.debug(f"WhatsApp self-reply guard: skipping msg in {chat_id} ({_now - _last:.1f}s after last reply)")
                        continue

                    # ── WhatsApp slash commands (for allowed users only) ──
                    if text.startswith("/") and self._is_allowed(user_id):
                        cmd = text.split()[0].lower().lstrip("/")
                        if cmd == "cost":
                            from ..session_db import get_cost_today, get_cost_week
                            today = get_cost_today()
                            week = get_cost_week()
                            response = (
                                f"*Cost Summary*\n"
                                f"Today: ${today:.2f}\n"
                                f"This week: ${week:.2f}"
                            )
                            await self.send(chat_id, response, reply_to=msg_key)
                            continue
                        elif cmd == "status":
                            from ..diagnostics import get_status_summary
                            s = get_status_summary()
                            response = (
                                f"*Status*\n"
                                f"Messages processed: {s['messages_processed']}\n"
                                f"Recent cost: ${s['total_cost_recent']:.4f}\n"
                                f"Avg latency: {s['avg_latency_ms']:.0f}ms\n"
                                f"Loop detections: {s['loop_detections']}\n"
                                f"Models: {', '.join(s['models_used']) or 'n/a'}"
                            )
                            await self.send(chat_id, response, reply_to=msg_key)
                            continue
                        elif cmd == "doctor":
                            from ..self_audit import run_audit
                            report = run_audit()
                            response = report.format_text()
                            await self.send(chat_id, response, reply_to=msg_key)
                            continue
                        elif cmd == "help":
                            response = (
                                "*Available commands*\n"
                                "/cost — Today & weekly cost summary\n"
                                "/status — Runtime diagnostics\n"
                                "/doctor — Self-audit report\n"
                                "/help — Show this list"
                            )
                            await self.send(chat_id, response, reply_to=msg_key)
                            continue

                    try:
                        # Build invoke text with any attached media
                        invoke_text = text

                        # Wrap served group messages with content sanitizer (prompt injection guard)
                        if is_served and not _is_agent_invoke:
                            from ..content_sanitizer import wrap_platform_message
                            invoke_text = wrap_platform_message(text, "whatsapp", sender=sender_name, is_served=True)

                        if image_path:
                            img_instruction = (
                                f"[The user sent an image. Read it at: {image_path}]\n"
                                "Analyze the image and respond. If it contains math, solve it step by step.\n"
                            )
                            invoke_text = img_instruction + (text if text else "What is in this image?")

                        elif file_path:
                            file_instruction = (
                                f"[The user sent a file: {file_name}. Read it at: {file_path}]\n"
                                "Read and analyze the file contents, then respond to the user.\n"
                            )
                            invoke_text = file_instruction + (text if text else f"Please read and summarize this file: {file_name}")

                        elif audio_path:
                            # Transcribe via whisper.cpp first, then send text to Claude
                            _force_reply_audio = True  # never NO_REPLY for voice messages
                            try:
                                from ..voice import speech_to_text
                                transcript = await speech_to_text(audio_path, language="auto")
                                if transcript:
                                    audio_instruction = (
                                        f"[The user sent a voice message. Transcript: \"{transcript}\"]\n"
                                        "You MUST respond to what they said. Do NOT use [NO_REPLY].\n"
                                        "Your response MUST have two parts:\n"
                                        "**Part 1 — Full Transcript**: Reproduce the COMPLETE transcript above, "
                                        "cleaned up for readability (fix punctuation, paragraphs) but preserving "
                                        "every sentence the speaker said. Do NOT summarize or skip anything.\n"
                                        "**Part 2 — Summary**: After the full transcript, provide your AI analysis/summary "
                                        "of the key points, organized by topic.\n"
                                    )
                                    invoke_text = audio_instruction + (text if text else "")
                                else:
                                    invoke_text = text if text else "[The user sent a voice message but transcription failed.]"
                            except Exception as e:
                                log.warning(f"WhatsApp audio transcription failed: {e}")
                                invoke_text = text if text else "[The user sent a voice message but transcription is unavailable.]"

                        # @agent invocations: force a response (never NO_REPLY)
                        if _is_agent_invoke:
                            invoke_text = (
                                "[DIRECT @agent INVOCATION by a user — you MUST respond. "
                                "Do NOT use [NO_REPLY]. The user explicitly asked for your help.]\n\n"
                                + invoke_text
                            )

                        # Debounce served group messages (not @agent, not media)
                        # Batches rapid-fire messages into one LLM call
                        if is_served and not _is_agent_invoke and not image_path and not file_path and not audio_path:
                            debounce_key = f"{chat_id}:{user_id}"
                            _msg_key_ref = msg_key  # capture for callback

                            async def _debounced_send(batched_text, _cid=chat_id, _uid=user_id, _mk=_msg_key_ref):
                                resp = await self.on_message("whatsapp", _cid, _uid, batched_text)
                                if resp:
                                    await self.send(_cid, resp, reply_to=_mk)
                                    self._last_reply_ts[_cid] = _time.monotonic()

                            self._debouncer.enqueue(debounce_key, invoke_text, _debounced_send)
                            continue  # don't invoke immediately

                        response = await self.on_message("whatsapp", chat_id, user_id, invoke_text)
                        if response:
                            await self.send(chat_id, response, reply_to=msg_key)
                            self._last_reply_ts[chat_id] = _time.monotonic()
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

                elif msg.get("type") == "history_messages":
                    # Route history fetch response to pending future
                    req_id = msg.get("request_id", "")
                    if req_id in self._pending_responses:
                        fut = self._pending_responses.pop(req_id)
                        if not fut.done():
                            fut.set_result(msg)

                elif msg.get("type") in ("groups", "contacts"):
                    # Route response to pending _send_command future
                    resp_type = msg["type"]
                    if resp_type in self._pending_responses:
                        fut = self._pending_responses.pop(resp_type)
                        if not fut.done():
                            fut.set_result(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _error_count += 1
                self._breaker.record_failure()
                if self._breaker.is_open():
                    log.warning(
                        f"WhatsApp read loop: circuit breaker open, "
                        f"sleeping {self._breaker.recovery_secs}s"
                    )
                    await asyncio.sleep(self._breaker.recovery_secs)
                    continue
                import random
                delay = min(_base_delay * (2 ** (_error_count - 1)), _max_delay)
                delay *= 1 + random.uniform(-0.2, 0.2)
                log.error(f"WhatsApp read loop error: {e} — retrying in {delay:.1f}s")
                await asyncio.sleep(delay)

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

    async def send(self, chat_id: str, text: str, reply_to: dict | None = None):
        if self.process and self.process.stdin:
            cmd: dict = {"type": "send", "chat_id": chat_id, "text": text}
            if reply_to:
                cmd["quoted"] = reply_to
            self.process.stdin.write((json.dumps(cmd) + "\n").encode())
            await self.process.stdin.drain()

    async def send_image(self, chat_id: str, image_path: str,
                         caption: str | None = None,
                         reply_to: dict | None = None):
        """Send an image file to a WhatsApp chat."""
        if self.process and self.process.stdin:
            cmd: dict = {
                "type": "send_image",
                "chat_id": chat_id,
                "image_path": image_path,
            }
            if caption:
                cmd["caption"] = caption
            if reply_to:
                cmd["quoted"] = reply_to
            self.process.stdin.write((json.dumps(cmd) + "\n").encode())
            await self.process.stdin.drain()
            log.info(f"Sent image to {chat_id}: {image_path}")

    async def _send_command(self, cmd: dict) -> dict | None:
        """Send a command to bridge.js and wait for a response of the expected type."""
        if not self.process or not self.process.stdin:
            return None
        self.process.stdin.write((json.dumps(cmd) + "\n").encode())
        await self.process.stdin.drain()
        # Wait for response (bridge emits it on stdout, read_loop stores it)
        # We use a simple future pattern
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

    async def fetch_messages(self, chat_id: str, count: int = 50) -> list[dict]:
        """Fetch historical messages for a chat via Baileys on-demand history sync.

        Returns list of message dicts. Requires at least one live message
        to have been seen in this chat (used as anchor for history request).
        Messages are also auto-stored in platform_messages.
        """
        import time
        request_id = f"fetch_{chat_id}_{int(time.time())}"

        if not self.process or not self.process.stdin:
            return []

        cmd = {
            "type": "fetch_messages",
            "chat_id": chat_id,
            "count": count,
            "request_id": request_id,
        }
        self.process.stdin.write((json.dumps(cmd) + "\n").encode())
        await self.process.stdin.drain()

        # Wait for response keyed by request_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_responses[request_id] = fut

        try:
            resp = await asyncio.wait_for(fut, timeout=40)  # 30s bridge + 10s buffer
        except asyncio.TimeoutError:
            self._pending_responses.pop(request_id, None)
            log.warning(f"fetch_messages timed out for {chat_id}")
            return []

        messages = resp.get("messages", []) if resp else []
        error = resp.get("error") if resp else None
        if error:
            log.info(f"fetch_messages for {chat_id}: {error}")

        # Store fetched messages in platform_messages (dedup by message_id)
        if messages:
            from ..session_db import store_platform_message
            from datetime import datetime, timezone
            stored = 0
            for m in messages:
                if m.get("from_me"):
                    continue  # Skip own messages for digest
                try:
                    # Convert unix timestamp to ISO format
                    ts = m.get("timestamp", 0)
                    if ts:
                        ts_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    else:
                        ts_iso = None
                    store_platform_message(
                        "whatsapp", m["chat_id"], m["user_id"],
                        m.get("sender_name", ""), m["text"],
                        message_id=m.get("message_id"),
                        timestamp=ts_iso,
                    )
                    stored += 1
                except Exception as e:
                    log.debug(f"Failed to store history message: {e}")
            log.info(f"fetch_messages: stored {stored}/{len(messages)} messages for {chat_id}")

        return messages
