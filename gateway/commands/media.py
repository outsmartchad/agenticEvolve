"""Media command handlers mixin — extracted from TelegramAdapter."""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..voice import text_to_speech, speech_to_text, list_voices, maybe_tts_reply, get_tts_config, TtsMode

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class MediaMixin:

    # ── /speak — text-to-speech ───────────────────────────────────

    async def _handle_speak(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Convert text to speech and send as Telegram voice message.

        Usage:
            /speak <text>           — convert text to voice (default voice)
            /speak --voice <name>   — use a specific edge-tts voice
            /speak --voices         — list available English voices
            /speak --mode <mode>    — set auto-TTS mode (off/always/inbound)
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []

        # /speak --voices — list voices
        if raw_args and raw_args[0] in ("--voices", "--list"):
            lang = raw_args[1] if len(raw_args) > 1 else "en"
            voices = await list_voices(lang)
            if not voices:
                await update.message.reply_text("No voices found.")
                return
            lines = [f"Edge TTS voices ({lang}):\n"]
            for v in voices[:30]:
                name = v.get("ShortName", "?")
                gender = v.get("Gender", "?")
                lines.append(f"  {name} ({gender})")
            if len(voices) > 30:
                lines.append(f"\n... and {len(voices) - 30} more")
            await update.message.reply_text("\n".join(lines))
            return

        # /speak --mode <off|always|inbound>
        if raw_args and raw_args[0] == "--mode":
            if len(raw_args) < 2:
                tts_cfg = get_tts_config(self._gateway.config if self._gateway else {})
                await update.message.reply_text(
                    f"Current TTS mode: {tts_cfg['mode']}\n"
                    f"Voice: {tts_cfg['voice']}\n\n"
                    "Modes:\n"
                    "  off — only /speak\n"
                    "  always — every reply gets voice\n"
                    "  inbound — reply with voice when you send voice"
                )
                return
            new_mode = raw_args[1].lower()
            if not TtsMode.is_valid(new_mode):
                await update.message.reply_text(f"Invalid mode: {new_mode}. Use: off, always, inbound")
                return
            # Update config in memory (hot-reload will persist on next config write)
            if self._gateway:
                if "tts" not in self._gateway.config:
                    self._gateway.config["tts"] = {}
                self._gateway.config["tts"]["mode"] = new_mode
            await update.message.reply_text(f"TTS mode set to: {new_mode}")
            return

        # Parse --voice flag
        flags = self._parse_flags(raw_args, {"--voice": {"type": "value"}})
        voice = flags.get("--voice") or None
        text = " ".join(raw_args)

        # If replying to a message, use that text
        if not text:
            reply_text, _ = self._get_reply_context(update)
            if reply_text:
                text = reply_text

        if not text:
            await update.message.reply_text(
                "*Usage:* `/speak <text>`\n\n"
                "*Options:*\n"
                "`--voice <name>` — use specific voice\n"
                "`--voices [lang]` — list voices\n"
                "`--mode <off|always|inbound>` — auto-TTS mode\n\n"
                "*Examples:*\n"
                "`/speak Hello, how are you today?`\n"
                "`/speak --voice en-US-GuyNeural Hey there!`\n"
                "`/speak --voices zh`\n\n"
                "Or reply to any message with `/speak` to voice it.",
                parse_mode="Markdown"
            )
            return

        # Get voice from config if not specified
        if not voice and self._gateway:
            tts_cfg = get_tts_config(self._gateway.config)
            voice = tts_cfg["voice"]

        await update.message.chat.send_action("record_voice")

        audio_path = await text_to_speech(text, voice=voice or "en-US-AndrewMultilingualNeural")

        if audio_path and audio_path.exists():
            try:
                with open(audio_path, "rb") as audio_file:
                    await update.message.reply_voice(
                        voice=audio_file,
                        caption=text[:200] if len(text) > 50 else None,
                    )
            except Exception as e:
                log.error(f"Failed to send voice: {e}")
                await update.message.reply_text(f"Failed to send voice message: {e}")
            finally:
                audio_path.unlink(missing_ok=True)
        else:
            await update.message.reply_text("TTS failed. Check logs.")

    # ── Voice/audio message handler ────────────────────────────────

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming voice messages — transcribe and process as text.

        Adapted from openclaw's audio-preflight + STT pipeline:
        1. Download voice/audio from Telegram
        2. Transcribe via Groq/OpenAI whisper
        3. Process transcript as regular message (with auto-TTS if mode=inbound)
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        # Get the voice or audio object
        voice = update.message.voice
        audio = update.message.audio
        media = voice or audio

        if not media:
            return

        duration = getattr(media, "duration", 0)
        file_size = getattr(media, "file_size", 0)

        # Download the audio file
        audio_dir = EXODIR / "tmp" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ext = ".ogg" if voice else ".mp3"
        audio_path = audio_dir / f"voice_{timestamp}_{media.file_id[:8]}{ext}"

        try:
            file = await context.bot.get_file(media.file_id)
            await file.download_to_drive(str(audio_path))
            log.info(f"Voice downloaded: {audio_path} ({file_size} bytes, {duration}s)")
        except Exception as e:
            log.error(f"Failed to download voice: {e}")
            await update.message.reply_text(f"Failed to download voice message: {e}")
            return

        # Transcribe
        await update.message.chat.send_action("typing")
        transcript = await speech_to_text(audio_path)

        if not transcript:
            await update.message.reply_text(
                "Could not transcribe voice message.\n"
                "Set GROQ_API_KEY (free) or OPENAI_API_KEY in .env for speech-to-text."
            )
            audio_path.unlink(missing_ok=True)
            return

        # Show transcript
        await update.message.reply_text(f"[Transcript]: {transcript}")

        # Process as regular message
        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)

        # Prepend voice context so Claude knows this is a transcribed voice message
        full_text = f"[The user sent a voice message. This is the transcript — treat it as if the user typed it directly]: {transcript}"
        reply_text, reply_urls = self._get_reply_context(update)
        if reply_text:
            full_text = f"[Replying to previous message: {reply_text[:1500]}]\n\n{transcript}"

        # Check for URLs — offer absorb/learn
        urls = self._extract_urls(full_text)
        if urls:
            non_url_text = full_text
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                await self._offer_absorb_learn(update, urls[0], "link in voice")
                audio_path.unlink(missing_ok=True)
                return

        # Regular chat with Claude
        typing_active = True
        async def keep_typing():
            while typing_active:
                try:
                    await update.message.chat.send_action("typing")
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(keep_typing())

        try:
            response = await self.on_message("telegram", chat_id, user_id, full_text)
            if response:
                # Check TTS auto-mode — if inbound, reply with voice too
                config = self._gateway.config if self._gateway else {}
                audio_reply, clean_response = await maybe_tts_reply(response, config, inbound_was_voice=True)

                if audio_reply and audio_reply.exists():
                    try:
                        # Send text first (with directives stripped), then voice
                        for i in range(0, len(clean_response), 4000):
                            await update.message.reply_text(clean_response[i:i+4000])
                        with open(audio_reply, "rb") as af:
                            await update.message.reply_voice(voice=af)
                    except Exception as e:
                        log.warning(f"Failed to send TTS reply: {e}")
                    finally:
                        audio_reply.unlink(missing_ok=True)
                else:
                    for i in range(0, len(clean_response), 4000):
                        await update.message.reply_text(clean_response[i:i+4000])
        except Exception as e:
            log.error(f"Voice processing error: {e}")
            await update.message.reply_text(f"Error: {e}")
        finally:
            typing_active = False
            typing_task.cancel()
            audio_path.unlink(missing_ok=True)

    # ── Photo/image handler ──────────────────────────────────────

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photos sent to the bot — download and pass to Claude for vision analysis.

        Workflow:
        1. Download highest-res photo to tmp/images/
        2. Build prompt with image path + caption + reply context
        3. Send to Claude (which uses Read tool to see the image)
        4. Auto-TTS if voice mode is active
        5. Offer absorb/learn if response contains URLs
        6. Cleanup temp image file
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        caption = update.message.caption or ""

        # If photo has a URL in the caption AND no other meaningful text, offer absorb/learn
        urls = self._extract_urls(caption) if caption else []
        if urls:
            non_url_text = caption
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                # Caption is just a URL — user wants to absorb/learn, not analyze the photo
                await self._offer_absorb_learn(update, urls[0], "link in image caption")
                return

        # Download the photo (get highest resolution)
        photo = update.message.photo[-1]  # largest size
        img_dir = EXODIR / "tmp" / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        img_path = img_dir / f"{timestamp}_{photo.file_id[:8]}.jpg"

        try:
            file = await context.bot.get_file(photo.file_id)
            await file.download_to_drive(str(img_path))
            log.info(f"Photo saved: {img_path} ({photo.width}x{photo.height})")
        except Exception as e:
            log.error(f"Failed to download photo: {e}")
            await update.message.reply_text(f"Failed to download image: {e}")
            return

        # Build prompt for Claude with the image path
        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)

        # Resolve reply-to context (user may be replying to a message with a photo)
        reply_text, reply_urls = self._get_reply_context(update)

        prompt = (
            f"[The user sent an image. It is saved at: {img_path}]\n"
            f"Read this image file and analyze it.\n"
        )
        if caption:
            prompt += f"\nUser's message with the image: {caption}\n"
        if reply_text:
            prompt += f"\n[This was sent as a reply to: {reply_text[:1500]}]\n"
        if not caption:
            prompt += (
                "\nDescribe what you see. If it's a screenshot of a tool, library, repo, "
                "or technical content, extract the key info (name, URL, purpose). "
                "If it contains code, transcribe and explain it."
            )

        # Keep typing indicator alive
        typing_active = True
        async def keep_typing():
            while typing_active:
                try:
                    await update.message.chat.send_action("typing")
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(keep_typing())

        try:
            response = await self.on_message("telegram", chat_id, user_id, prompt)
            if response:
                # Check TTS auto-mode
                config = self._gateway.config if self._gateway else {}
                audio_reply, clean_response = await maybe_tts_reply(response, config, inbound_was_voice=False)

                # Check if response mentions a URL or tool — offer absorb/learn
                resp_urls = self._extract_urls(clean_response)

                if audio_reply and audio_reply.exists():
                    try:
                        for i in range(0, len(clean_response), 4000):
                            await update.message.reply_text(clean_response[i:i+4000])
                        with open(audio_reply, "rb") as af:
                            await update.message.reply_voice(voice=af)
                    except Exception as e:
                        log.warning(f"Failed to send TTS reply for photo: {e}")
                    finally:
                        audio_reply.unlink(missing_ok=True)
                else:
                    for i in range(0, len(clean_response), 4000):
                        await update.message.reply_text(clean_response[i:i+4000])

                if resp_urls:
                    await self._offer_absorb_learn(update, resp_urls[0], "tool/repo detected in image")
        except Exception as e:
            log.error(f"Photo processing error: {e}")
            await update.message.reply_text(f"Error processing image: {e}")
        finally:
            typing_active = False
            typing_task.cancel()
            # Cleanup temp image
            try:
                img_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ── Document/file handler ──────────────────────────────────────

    async def _handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle documents sent to the bot — download and pass to Claude for analysis.

        Supports: PDFs, code files, text files, images sent as documents, etc.
        Claude's Read tool can handle images, PDFs, and text files natively.

        Workflow:
        1. Download document to tmp/documents/
        2. Build prompt with file path + caption + reply context
        3. Send to Claude (which uses Read tool to analyze the file)
        4. Offer absorb/learn if response contains URLs
        5. Cleanup temp file
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        doc = update.message.document
        if not doc:
            return

        caption = update.message.caption or ""

        # If caption is just a URL, offer absorb/learn
        urls = self._extract_urls(caption) if caption else []
        if urls:
            non_url_text = caption
            for url in urls:
                non_url_text = non_url_text.replace(url, "").strip()
            if len(non_url_text) < 30:
                await self._offer_absorb_learn(update, urls[0], "link in document caption")
                return

        # Size guard — skip files > 50MB
        file_size = doc.file_size or 0
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(
                f"File too large ({file_size / 1024 / 1024:.1f} MB). Max supported: 50 MB."
            )
            return

        # Download the document
        doc_dir = EXODIR / "tmp" / "documents"
        doc_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        original_name = doc.file_name or "unnamed"
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in original_name)
        doc_path = doc_dir / f"{timestamp}_{safe_name}"

        try:
            file = await context.bot.get_file(doc.file_id)
            await file.download_to_drive(str(doc_path))
            log.info(f"Document saved: {doc_path} ({file_size} bytes, mime={doc.mime_type})")
        except Exception as e:
            log.error(f"Failed to download document: {e}")
            await update.message.reply_text(f"Failed to download file: {e}")
            return

        # Build prompt for Claude with the file path
        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)

        # Resolve reply-to context
        reply_text, reply_urls = self._get_reply_context(update)

        # Determine file type hint
        mime = doc.mime_type or ""
        if mime.startswith("image/"):
            file_hint = "image file"
        elif mime == "application/pdf":
            file_hint = "PDF document"
        elif mime.startswith("text/") or mime in ("application/json", "application/xml", "application/javascript"):
            file_hint = "text/code file"
        elif any(safe_name.endswith(ext) for ext in (".py", ".ts", ".js", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".sol", ".md", ".txt", ".csv", ".toml", ".yaml", ".yml", ".json", ".xml", ".html", ".css", ".sh", ".sql")):
            file_hint = "text/code file"
        else:
            file_hint = f"file (MIME: {mime})" if mime else "file"

        prompt = (
            f"[The user sent a {file_hint}: \"{original_name}\" saved at: {doc_path}]\n"
            f"Read this file and analyze its contents.\n"
        )
        if caption:
            prompt += f"\nUser's message with the file: {caption}\n"
        if reply_text:
            prompt += f"\n[This was sent as a reply to: {reply_text[:1500]}]\n"
        if not caption:
            prompt += (
                "\nProvide a summary of the file contents. If it's code, explain what it does. "
                "If it's a PDF or document, extract key information. "
                "If it's an image, describe what you see."
            )

        # Keep typing indicator alive
        typing_active = True
        async def keep_typing():
            while typing_active:
                try:
                    await update.message.chat.send_action("typing")
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(keep_typing())

        try:
            response = await self.on_message("telegram", chat_id, user_id, prompt)
            if response:
                # Check if response mentions a URL or tool — offer absorb/learn
                resp_urls = self._extract_urls(response)
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
                if resp_urls:
                    await self._offer_absorb_learn(update, resp_urls[0], "tool/repo detected in document")
        except Exception as e:
            log.error(f"Document processing error: {e}")
            await update.message.reply_text(f"Error processing file: {e}")
        finally:
            typing_active = False
            typing_task.cancel()
            # Cleanup temp document
            try:
                doc_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ── /screenshot — capture URL and send as photo ───────────────

    async def _handle_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Capture a URL screenshot and send it as a Telegram photo.

        Usage:
            /screenshot <url>           — screenshot at 1280x800
            /screenshot <url> --full    — full-page screenshot
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = list(context.args) if context.args else []
        if not args:
            await update.message.reply_text(
                "Usage: /screenshot <url> [--full]\n"
                "Example: /screenshot https://example.com"
            )
            return

        full_page = "--full" in args
        url = next((a for a in args if not a.startswith("--")), None)
        if not url:
            await update.message.reply_text("Please provide a URL.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        status_msg = await update.message.reply_text(f"Screenshotting {url} ...")

        try:
            from playwright.async_api import async_playwright
            import tempfile

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(url, wait_until="networkidle", timeout=30000)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    tmp_path = f.name
                await page.screenshot(path=tmp_path, full_page=full_page)
                await browser.close()

            with open(tmp_path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=url[:1024],
                )
            Path(tmp_path).unlink(missing_ok=True)
            await status_msg.delete()

        except Exception as e:
            log.error(f"Screenshot failed for {url}: {e}")
            await status_msg.edit_text(f"Screenshot failed: {e}")
