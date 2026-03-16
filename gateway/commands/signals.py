"""Signal-related command handlers: produce, wechat, whatsapp, discord, digest, reflect."""
from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Callable

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"
CRON_DIR = EXODIR / "cron"
CRON_JOBS_FILE = CRON_DIR / "jobs.json"

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class SignalsMixin:

    # ── /produce — brainstorm business ideas from latest signals ──────

    async def _handle_produce(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aggregate all signal sources and brainstorm app/business ideas.

        Usage: /produce [--model X] [--ideas N]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--model": {"type": "value"},
            "--ideas": {"type": "value", "cast": int, "default": 5},
        })
        num_ideas = max(1, min(flags["--ideas"], 10))
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        lang_instruction = self._get_lang_instruction(user_id)
        await update.message.reply_text(
            f"Aggregating signals from all sources...\n"
            f"Brainstorming {num_ideas} business ideas.\n~2-4 min."
        )

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        start_reporter()
        try:
            result_text, cost = await loop.run_in_executor(
                None, lambda: self._build_produce(num_ideas, model, on_progress_sync, lang_instruction)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Generate error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Generate failed: {e}")
            return
        finally:
            stop_reporter()

        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_text = result_text + footer
        for i in range(0, len(full_text), 4000):
            chunk = full_text[i:i + 4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "produce", cost)

    def _build_produce(self, num_ideas: int, model: str,
                        on_progress: Callable, lang_instruction: str = "") -> tuple[str, float]:
        """Aggregate signals and brainstorm business ideas. Runs in executor thread."""
        import glob as _glob
        from datetime import datetime as _dt

        signals_dir = Path.home() / ".agenticEvolve" / "signals"
        today = _dt.now().strftime("%Y-%m-%d")
        today_dir = signals_dir / today

        # Collect all signal files from today
        all_signals = []
        source_counts = {}

        if today_dir.exists():
            for f in sorted(today_dir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, list):
                        signals = data
                    else:
                        signals = [data]

                    source_name = f.stem
                    source_counts[source_name] = len(signals)
                    all_signals.extend(signals)
                except Exception:
                    continue

        if not all_signals:
            # Try to collect fresh signals
            on_progress("No signals found for today. Run /evolve first to collect signals.")
            return "No signals found for today. Run `/evolve --dry-run` first to collect fresh data from all sources.", 0.0

        on_progress(f"Loaded {len(all_signals)} signals from {len(source_counts)} sources")

        # Build a condensed summary of all signals for the prompt
        # Group by source, take top items by engagement
        source_summaries = []
        for source_name, count in sorted(source_counts.items()):
            source_signals = [s for s in all_signals if s.get("id", "").startswith(source_name.split("-")[0]) or
                              source_name in str(s.get("metadata", {}).get("relevance_tags", []))]
            if not source_signals:
                # fallback: match by source field
                source_signals = [s for s in all_signals
                                  if s.get("source", "") == source_name.replace("-", "")
                                  or s.get("source", "") == source_name]

            # Sort by engagement
            source_signals.sort(
                key=lambda x: (x.get("metadata", {}).get("points", 0)
                               or x.get("metadata", {}).get("stars", 0)
                               or x.get("metadata", {}).get("likes", 0)
                               or x.get("metadata", {}).get("replies", 0)
                               or 0),
                reverse=True
            )

            items = []
            for s in source_signals[:8]:
                title = s.get("title", "")
                content = s.get("content", "")[:200]
                url = s.get("url", "")
                meta = s.get("metadata", {})
                engagement = meta.get("points", 0) or meta.get("stars", 0) or meta.get("likes", 0) or 0
                items.append(f"  - {title} ({engagement} pts) {url}\n    {content}")

            if items:
                source_summaries.append(f"### {source_name} ({count} signals)\n" + "\n".join(items))

        signals_text = "\n\n".join(source_summaries)

        # Truncate to avoid context overflow
        if len(signals_text) > 40000:
            signals_text = signals_text[:40000] + "\n\n... (truncated)"

        on_progress("Brainstorming ideas...")

        from ..agent import invoke_claude_streaming

        prompt = (
            f"You are Vincent's personal AI business strategist.\n\n"
            f"Vincent is a developer who builds AI agents, onchain infrastructure, and developer tools. "
            f"He's looking for actionable app/business ideas he can build quickly (days to weeks, not months) "
            f"and monetize.\n\n"
            f"Here are the latest signals from {len(source_counts)} sources "
            f"({len(all_signals)} total signals):\n\n"
            f"{signals_text}\n\n"
            f"Based on these trends, generate exactly {num_ideas} concrete business/app ideas.\n\n"
            f"For EACH idea, provide:\n\n"
            f"## Idea N: [Name]\n"
            f"**One-liner**: What it does in one sentence\n"
            f"**Why now**: What trend/signal makes this timely (cite specific signals)\n"
            f"**Target users**: Who pays for this\n"
            f"**Revenue model**: How it makes money (be specific — pricing, tiers)\n"
            f"**Tech stack**: What to build with (leverage Vincent's skills: TypeScript, Python, Claude API, Solana, React/Next.js)\n"
            f"**MVP scope**: What to build in week 1 to validate\n"
            f"**Competitive moat**: Why this is hard to copy\n"
            f"**Estimated effort**: Days/weeks to MVP\n"
            f"**Revenue potential**: Realistic monthly revenue at 6 months\n\n"
            f"Prioritize ideas that:\n"
            f"- Solve a real pain point visible in the signals\n"
            f"- Can be built solo by one developer\n"
            f"- Have a clear path to first $1000/month\n"
            f"- Leverage AI/LLM trends (Vincent's strength)\n"
            f"- Are NOT just another chatbot wrapper\n\n"
            f"Rank ideas by feasibility × market timing × revenue potential.\n"
            f"Be brutally honest about risks and challenges for each.\n"
            f"Use Markdown formatting."
            + lang_instruction
        )

        result = invoke_claude_streaming(
            prompt,
            on_progress=on_progress,
            model=model,
            session_context=f"[Generate: {num_ideas} ideas from {len(all_signals)} signals]"
        )

        text = result.get("text", "No ideas generated.")
        cost = result.get("cost", 0.0)

        sources_line = ", ".join(f"{k}({v})" for k, v in sorted(source_counts.items()))
        header = (
            f"*Business Ideas — based on {len(all_signals)} signals*\n"
            f"Sources: {sources_line}\n\n"
        )
        return header + text, cost

    # ── /wechat — WeChat group chat digest ────────────────────────────

    async def _handle_wechat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Summarize recent WeChat group chat messages with AI analysis.

        Usage: /wechat [--hours N] [--model X]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--hours": {"type": "value", "cast": int, "default": 24},
            "--model": {"type": "value"},
        })
        hours = max(1, min(flags["--hours"], 168))  # max 7 days
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        lang_instruction = self._get_lang_instruction(user_id)
        await update.message.reply_text(f"Reading WeChat groups (last {hours}h)...\n~1-2 min.")

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        start_reporter()
        try:
            summary, cost = await loop.run_in_executor(
                None, lambda: self._build_wechat_digest(hours, model, on_progress_sync, lang_instruction, user_id)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"WeChat digest error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"WeChat digest failed: {e}")
            return
        finally:
            stop_reporter()

        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_text = summary + footer
        for i in range(0, len(full_text), 4000):
            chunk = full_text[i:i + 4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "wechat-digest", cost)

        # Retro: mandatory reflection after WeChat digest
        try:
            from ..retro import run_retro
            retro_text, retro_cost = await loop.run_in_executor(
                None,
                lambda: run_retro("wechat", summary,
                                  on_progress=lambda m: None,
                                  model="claude-sonnet-4-6")
            )
            retro_msg = f"*Retro*\n{retro_text}\n\n(${retro_cost:.3f})"
            for i in range(0, len(retro_msg), 4000):
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=retro_msg[i:i + 4000],
                        parse_mode="Markdown"
                    )
                except Exception:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=retro_msg[i:i + 4000]
                    )
            if retro_cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "wechat-retro", retro_cost)
        except Exception as e:
            log.warning(f"Retro after /wechat failed (non-fatal): {e}")

    def _auto_refresh_wechat_dbs(self, tools_dir, decrypted_dir, on_progress: Callable):
        """Auto-refresh decrypted WeChat DBs if stale (> 2 hours).

        Runs sudo find_keys (passwordless via sudoers) + decrypt_db.py.
        """
        import subprocess
        import time

        msg_db = decrypted_dir / "message" / "message_0.db"
        keys_file = tools_dir / "wechat_keys.json"
        max_age = 2 * 3600  # 2 hours

        # Check if DBs are fresh enough
        if msg_db.exists():
            age = time.time() - msg_db.stat().st_mtime
            if age < max_age:
                return  # DBs are fresh

        on_progress("WeChat DBs are stale, refreshing...")

        # Step 1: Run find_keys (passwordless sudo)
        find_keys = tools_dir / "find_keys"
        if find_keys.exists():
            try:
                result = subprocess.run(
                    ["sudo", str(find_keys)],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(tools_dir),
                )
                if result.returncode == 0:
                    on_progress("Keys extracted successfully")
                else:
                    log.warning(f"find_keys failed (rc={result.returncode}): {result.stderr[:200]}")
                    if not keys_file.exists():
                        on_progress("Key extraction failed and no cached keys — cannot decrypt")
                        return
                    on_progress("find_keys failed, using cached keys")
            except subprocess.TimeoutExpired:
                log.warning("find_keys timed out")
                if not keys_file.exists():
                    return
            except Exception as e:
                log.warning(f"find_keys error: {e}")
                if not keys_file.exists():
                    return

        if not keys_file.exists():
            on_progress("No wechat_keys.json — cannot decrypt. Run sudo find_keys manually.")
            return

        # Step 2: Run decrypt_db.py (no sudo needed)
        import sys
        decrypt_script = tools_dir / "decrypt_db.py"
        if decrypt_script.exists():
            try:
                result = subprocess.run(
                    [sys.executable, str(decrypt_script),
                     "--keys", str(keys_file),
                     "--output", str(decrypted_dir)],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(tools_dir),
                )
                if result.returncode == 0:
                    on_progress("WeChat DBs refreshed successfully")
                else:
                    log.warning(f"decrypt_db.py failed: {result.stderr[:200]}")
                    on_progress("Decrypt failed, using stale data")
            except Exception as e:
                log.warning(f"decrypt_db.py error: {e}")
                on_progress("Decrypt error, using stale data")

    def _build_wechat_digest(self, hours: int, model: str,
                             on_progress: Callable, lang_instruction: str = "",
                             user_id: str = "") -> tuple[str, float]:
        """Build WeChat group chat digest using Claude. Runs in executor thread.

        If user_id is provided, filters to only subscribed groups.
        """
        from pathlib import Path as _Path
        import sys

        tools_dir = _Path.home() / ".agenticEvolve" / "tools" / "wechat-decrypt"
        decrypted_dir = tools_dir / "decrypted"

        # Auto-refresh if DBs are stale (> 2 hours old) or missing
        self._auto_refresh_wechat_dbs(tools_dir, decrypted_dir, on_progress)

        if not decrypted_dir.exists():
            return ("No decrypted WeChat data found.\n"
                    "Run the decrypt pipeline first:\n"
                    "  `cd ~/.agenticEvolve/tools/wechat-decrypt`\n"
                    "  `sudo ./find_keys && python3 decrypt_db.py`"), 0.0

        # Load messages via collector
        collectors_dir = str(_Path.home() / ".agenticEvolve" / "collectors")
        if collectors_dir not in sys.path:
            sys.path.insert(0, collectors_dir)

        try:
            # Import from the wechat module using its path
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "wechat_collector",
                str(_Path.home() / ".agenticEvolve" / "collectors" / "wechat.py")
            )
            wechat_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wechat_mod)
            signals = wechat_mod.extract_group_messages(decrypted_dir, hours=hours)
        except Exception as e:
            return f"Failed to read WeChat messages: {e}", 0.0

        # Filter by subscriptions if user has any
        if user_id:
            from ..session_db import get_subscriptions
            subs = get_subscriptions(user_id, mode="subscribe", platform="wechat")
            if subs:
                sub_ids = {s["target_id"] for s in subs}
                signals = [s for s in signals
                           if s.get("metadata", {}).get("group_id") in sub_ids]
                on_progress(f"Filtered to {len(signals)} subscribed groups "
                            f"(out of {len(sub_ids)} subscriptions)")

        if not signals:
            return f"No WeChat group messages in the last {hours} hours.", 0.0

        # Build conversation text
        chat_lines = []
        total_msgs = 0
        for s in signals:
            meta = s.get("metadata", {})
            chat_lines.append(f"## {meta.get('group_name', 'Unknown')} "
                              f"({meta.get('message_count', 0)} msgs, "
                              f"{meta.get('unique_senders', 0)} senders)")
            chat_lines.append(s.get("content", ""))
            chat_lines.append("")
            total_msgs += meta.get("message_count", 0)

        chat_text = "\n".join(chat_lines)

        # Truncate to avoid context overflow
        if len(chat_text) > 30000:
            chat_text = chat_text[:30000] + "\n\n... (truncated)"

        on_progress("Analyzing conversations...")

        from ..agent import invoke_claude_streaming

        prompt = (
            f"You are Vincent's personal AI assistant analyzing his WeChat group chats.\n\n"
            f"Here are the last {hours} hours of group conversations ({total_msgs} messages "
            f"across {len(signals)} groups):\n\n"
            f"{chat_text}\n\n"
            f"Create a concise, actionable digest. IMPORTANT: Summarize EACH GROUP SEPARATELY.\n\n"
            f"For EACH group, use this structure:\n\n"
            f"---\n"
            f"## [Group Name] (N messages, N senders)\n\n"
            f"**关键要点** (3-5 bullet points — the most important things from THIS group)\n\n"
            f"**提到的工具 & 仓库** (list with brief descriptions, include URLs if shared)\n\n"
            f"**技术洞察** (useful tips, patterns, debugging techniques)\n\n"
            f"**热议话题** (what people are talking about most in this group)\n\n"
            f"---\n\n"
            f"After all groups, add a final section:\n\n"
            f"## Vincent 的 Action Items\n"
            f"(Combined actionable items across ALL groups, prioritized)\n\n"
            f"Be concise. Skip small talk and irrelevant messages. Focus on signal, not noise.\n"
            f"Use Markdown formatting. ALWAYS respond in simplified Chinese (简体中文) since the messages are from Chinese group chats."
            + (lang_instruction if lang_instruction else "")
        )

        result = invoke_claude_streaming(
            prompt,
            on_progress=on_progress,
            model=model,
            session_context=f"[WeChat digest: {hours}h, {len(signals)} groups]"
        )

        text = result.get("text", "No analysis generated.")
        cost = result.get("cost", 0.0)

        header = f"*WeChat Digest — last {hours}h*\n{total_msgs} messages across {len(signals)} groups\n\n"
        return header + text, cost

    async def _send_wechat_digest(self, chat_id: str, hours: int = 24):
        """Send a WeChat digest to a specific chat. Called by cron."""
        model = self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet"

        def _noop(msg):
            pass

        summary, cost = self._build_wechat_digest(hours, model, _noop)

        if self.app and self.app.bot:
            for i in range(0, len(summary), 4000):
                chunk = summary[i:i + 4000]
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                    )
                except Exception:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

    # ── /discord — Discord channel digest ─────────────────────────────

    async def _handle_discord(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Summarize recent Discord messages from subscribed channels.

        Usage: /discord [--hours N] [--model X]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--hours": {"type": "value", "cast": int, "default": 24},
            "--model": {"type": "value"},
        })
        hours = max(1, min(flags["--hours"], 168))
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        lang_instruction = self._get_lang_instruction(user_id)

        # Check subscriptions
        from ..session_db import get_subscriptions
        subs = get_subscriptions(user_id, mode="subscribe", platform="discord")
        if not subs:
            await update.message.reply_text(
                "No Discord channels subscribed.\n"
                "Use /subscribe → Discord to select channels first."
            )
            return

        await update.message.reply_text(
            f"Reading {len(subs)} Discord channels (last {hours}h)...\n~1-2 min."
        )

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        start_reporter()
        try:
            summary, cost = await self._build_discord_digest(
                subs, hours, model, on_progress_sync, lang_instruction
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Discord digest error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Discord digest failed: {e}")
            return
        finally:
            stop_reporter()

        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_text = summary + footer
        for i in range(0, len(full_text), 4000):
            chunk = full_text[i:i + 4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "discord-digest", cost)

    async def _build_discord_digest(self, subs: list[dict], hours: int,
                                     model: str, on_progress: Callable,
                                     lang_instruction: str = "") -> tuple[str, float]:
        """Fetch messages from subscribed Discord channels and summarize."""
        adapter = None
        if self._gateway:
            for a in self._gateway.adapters:
                if a.name == "discord":
                    adapter = a
                    break

        if not adapter or not hasattr(adapter, "get_messages"):
            return "Discord adapter not connected.", 0.0

        # Compute Discord snowflake ID for N hours ago
        # Discord epoch: 2015-01-01T00:00:00Z = 1420070400000 ms
        import time
        discord_epoch = 1420070400000
        cutoff_ms = int((time.time() - hours * 3600) * 1000)
        after_snowflake = str((cutoff_ms - discord_epoch) << 22)

        # Fetch messages from each subscribed channel
        all_channels = []
        for sub in subs:
            channel_id = sub["target_id"]
            channel_name = sub.get("target_name", channel_id)
            on_progress(f"Fetching #{channel_name}...")

            try:
                # Fetch up to 100 messages (2 pages of 50)
                msgs = await adapter.get_messages(channel_id, after=after_snowflake, limit=50)
                if len(msgs) == 50:
                    last_id = msgs[-1]["id"]
                    more = await adapter.get_messages(channel_id, after=last_id, limit=50)
                    msgs.extend(more)
            except Exception as e:
                log.warning(f"Failed to fetch #{channel_name}: {e}")
                continue

            if msgs:
                all_channels.append({
                    "name": channel_name,
                    "messages": msgs,
                    "count": len(msgs),
                })

        if not all_channels:
            return f"No Discord messages in the last {hours} hours from subscribed channels.", 0.0

        # Build text for Claude
        total_msgs = sum(c["count"] for c in all_channels)
        chat_lines = []
        for ch in all_channels:
            chat_lines.append(f"## #{ch['name']} ({ch['count']} messages)")
            for m in ch["messages"]:
                ts = m.get("timestamp", "")[:16]
                content = m.get("content", "")
                if content:
                    chat_lines.append(f"[{ts}] {m['author']}: {content}")
            chat_lines.append("")

        chat_text = "\n".join(chat_lines)
        if len(chat_text) > 30000:
            chat_text = chat_text[:30000] + "\n\n... (truncated)"

        on_progress(f"Analyzing {total_msgs} messages across {len(all_channels)} channels...")

        from ..agent import invoke_claude_streaming

        prompt = (
            f"You are Vincent's personal AI assistant analyzing his Discord messages.\n\n"
            f"Here are the last {hours} hours of messages ({total_msgs} messages "
            f"across {len(all_channels)} channels):\n\n"
            f"{chat_text}\n\n"
            f"Create a concise, actionable digest. Summarize EACH CHANNEL SEPARATELY.\n\n"
            f"For EACH channel, use this structure:\n\n"
            f"---\n"
            f"## #[Channel Name] (N messages)\n\n"
            f"**Key Takeaways** (3-5 bullet points)\n\n"
            f"**Tools & Repos Mentioned** (list with brief descriptions, include URLs if shared)\n\n"
            f"**Notable Discussions** (what people are talking about most)\n\n"
            f"---\n\n"
            f"After all channels, add:\n\n"
            f"## Action Items\n"
            f"(Combined actionable items across ALL channels, prioritized)\n\n"
            f"Be concise. Skip noise. Focus on signal.\n"
            f"Use Markdown formatting."
            + (lang_instruction if lang_instruction else "")
        )

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: invoke_claude_streaming(
                prompt,
                on_progress=on_progress,
                model=model,
                session_context=f"[Discord digest: {hours}h, {len(all_channels)} channels]"
            )
        )

        text = result.get("text", "No analysis generated.")
        cost = result.get("cost", 0.0)

        header = f"*Discord Digest — last {hours}h*\n{total_msgs} messages across {len(all_channels)} channels\n\n"
        return header + text, cost

    # ── /whatsapp — WhatsApp digest ─────────────────────────────────

    async def _handle_whatsapp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Summarize recent WhatsApp messages from served/subscribed groups.

        Usage: /whatsapp [--hours N] [--model X]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--hours": {"type": "value", "cast": int, "default": 24},
            "--model": {"type": "value"},
        })
        hours = max(1, min(flags["--hours"], 168))
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        lang_instruction = self._get_lang_instruction(user_id)

        # Get all subscribed + served WhatsApp groups
        from ..session_db import get_subscriptions, get_serve_targets, get_platform_messages
        subs = get_subscriptions(user_id, mode="subscribe", platform="whatsapp")
        serves = get_serve_targets("whatsapp")
        all_ids = {s["target_id"] for s in subs} | {t["target_id"] for t in serves}
        all_names = {}
        for s in subs:
            all_names[s["target_id"]] = s.get("target_name", s["target_id"])
        for t in serves:
            all_names[t["target_id"]] = t.get("target_name", t["target_id"])

        if not all_ids:
            await update.message.reply_text(
                "No WhatsApp groups subscribed or served.\n"
                "Use /subscribe or /serve → WhatsApp to select groups first."
            )
            return

        # Try to backfill historical messages via bridge before checking stored messages
        wa_adapter = None
        if self._gateway:
            for a in self._gateway.adapters:
                if a.name == "whatsapp" and hasattr(a, "fetch_messages"):
                    wa_adapter = a
                    break

        if wa_adapter:
            await update.message.reply_text(
                f"Fetching historical messages for {len(all_ids)} groups...\n"
                "This requires your phone to be online."
            )
            fetch_count = 0
            for gid in all_ids:
                try:
                    fetched = await wa_adapter.fetch_messages(gid, count=50)
                    fetch_count += len(fetched)
                except Exception as e:
                    log.debug(f"fetch_messages failed for {gid}: {e}")
            if fetch_count > 0:
                log.info(f"/whatsapp: backfilled {fetch_count} historical messages")

        # Fetch stored messages (includes any just-backfilled ones)
        messages = get_platform_messages("whatsapp", list(all_ids), hours=hours)
        if not messages:
            await update.message.reply_text(
                f"No WhatsApp messages in the last {hours} hours.\n\n"
                "Possible reasons:\n"
                "- No messages were sent in subscribed groups\n"
                "- Gateway wasn't running and no anchor messages exist for history fetch\n"
                "- Your phone was offline during history fetch\n\n"
                "Messages accumulate automatically while the gateway runs."
            )
            return

        await update.message.reply_text(
            f"Analyzing {len(messages)} WhatsApp messages (last {hours}h)...\n~1-2 min."
        )

        # Group messages by chat
        from collections import defaultdict
        by_chat = defaultdict(list)
        for m in messages:
            by_chat[m["chat_id"]].append(m)

        # Build text for Claude
        chat_lines = []
        for cid, msgs in by_chat.items():
            name = all_names.get(cid, cid)
            chat_lines.append(f"## {name} ({len(msgs)} messages)")
            for m in msgs:
                ts = m["timestamp"][:16]
                sender = m.get("sender_name") or m["user_id"].split("@")[0]
                chat_lines.append(f"[{ts}] {sender}: {m['content']}")
            chat_lines.append("")

        chat_text = "\n".join(chat_lines)
        if len(chat_text) > 30000:
            chat_text = chat_text[:30000] + "\n\n... (truncated)"

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        start_reporter()
        try:
            from ..agent import invoke_claude_streaming
            prompt = (
                f"You are analyzing WhatsApp group chat messages.\n\n"
                f"Here are the last {hours} hours of messages ({len(messages)} total "
                f"across {len(by_chat)} groups):\n\n"
                f"{chat_text}\n\n"
                f"Create a concise, actionable digest. Summarize EACH GROUP SEPARATELY.\n\n"
                f"For EACH group:\n"
                f"## [Group Name] (N messages)\n"
                f"**Key Topics** (3-5 bullet points)\n"
                f"**Notable Links/Resources** (if any were shared)\n"
                f"**Action Items** (if any)\n\n"
                f"Be concise. Skip noise. Focus on signal.\n"
                f"Use Markdown formatting."
                + (lang_instruction if lang_instruction else "")
            )

            result = await loop.run_in_executor(
                None,
                lambda: invoke_claude_streaming(
                    prompt,
                    on_progress=on_progress_sync,
                    model=model,
                    session_context=f"[WhatsApp digest: {hours}h, {len(by_chat)} groups]"
                )
            )
        except Exception as e:
            stop_reporter()
            log.error(f"WhatsApp digest error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"WhatsApp digest failed: {e}")
            return
        finally:
            stop_reporter()

        text = result.get("text", "No analysis generated.")
        cost = result.get("cost", 0.0)
        tools_used = get_tool_count()
        header = f"*WhatsApp Digest — last {hours}h*\n{len(messages)} messages across {len(by_chat)} groups\n\n"
        full_text = header + text + f"\n\n({tools_used} steps, ${cost:.2f})"

        for i in range(0, len(full_text), 4000):
            chunk = full_text[i:i + 4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "whatsapp-digest", cost)

    # ── /digest — morning briefing ──────────────────────────────────

    async def _handle_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a morning briefing: top signals, skills built, sessions, cost.

        Usage: /digest [--days N]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--days": {"type": "value", "cast": int, "default": 1},
        })
        days = max(1, min(flags["--days"], 7))

        chat_id = str(update.message.chat_id)
        await update.message.reply_text(f"Building digest (last {days}d)...")
        await self._send_digest(chat_id, days=days)

    async def _send_digest(self, chat_id: str, days: int = 1):
        """Build and send the digest message. Called by command or cron."""
        import sqlite3
        from ..agent import get_today_cost
        from ..session_db import DB_PATH

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        since_str = since.isoformat()

        # ── Sessions since cutoff ──
        sessions_summary = ""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT title, message_count, source, started_at FROM sessions "
                "WHERE started_at >= ? ORDER BY started_at DESC LIMIT 20",
                (since_str,)
            ).fetchall()
            conn.close()
            if rows:
                lines = []
                for r in rows:
                    title = (r["title"] or "(untitled)")[:50]
                    msgs = r["message_count"]
                    ts = r["started_at"][:16]
                    lines.append(f"  {ts} — {title} ({msgs} msgs)")
                sessions_summary = "\n".join(lines)
            else:
                sessions_summary = "  (none)"
        except Exception:
            sessions_summary = "  (error reading sessions)"

        # ── Top signals from today's signal dir ──
        signals_summary = ""
        try:
            today_str = now.strftime("%Y-%m-%d")
            sig_dir = EXODIR / "signals" / today_str
            if not sig_dir.exists():
                # Fall back to most recent signal dir
                sig_dirs = sorted((EXODIR / "signals").glob("????-??-??")) if (EXODIR / "signals").exists() else []
                sig_dir = sig_dirs[-1] if sig_dirs else None

            if sig_dir and sig_dir.exists():
                import json as _json
                signal_lines = []
                for f in sorted(sig_dir.glob("*.json"))[:3]:
                    try:
                        content = f.read_text().strip()
                        for line in content.splitlines()[:5]:
                            if not line.strip():
                                continue
                            obj = _json.loads(line)
                            title = obj.get("title", obj.get("name", ""))[:60]
                            source = obj.get("source", f.stem)
                            if title:
                                signal_lines.append(f"  [{source}] {title}")
                    except Exception:
                        pass
                signals_summary = "\n".join(signal_lines[:5]) if signal_lines else "  (none today)"
            else:
                signals_summary = "  (no signal dir found)"
        except Exception:
            signals_summary = "  (error reading signals)"

        # ── Skills built since cutoff ──
        skills_built = ""
        try:
            skills_dir = Path.home() / ".claude" / "skills"
            if skills_dir.exists():
                new_skills = []
                for skill_path in skills_dir.glob("*/SKILL.md"):
                    mtime = datetime.fromtimestamp(skill_path.stat().st_mtime, tz=timezone.utc)
                    if mtime >= since:
                        new_skills.append(skill_path.parent.name)
                skills_built = "\n".join(f"  {s}" for s in new_skills) if new_skills else "  (none)"
            else:
                skills_built = "  (no skills dir)"
        except Exception:
            skills_built = "  (error)"

        # ── Cost ──
        cost_today = get_today_cost()

        # ── Cron job next runs ──
        cron_summary = ""
        try:
            import json as _json
            if CRON_JOBS_FILE.exists():
                jobs = _json.loads(CRON_JOBS_FILE.read_text())
                active = [j for j in jobs if not j.get("paused")]
                lines = []
                for j in active[:5]:
                    nxt = j.get("next_run_at", "?")[:16]
                    jid = j.get("id", "?")
                    lines.append(f"  {jid} → {nxt}")
                cron_summary = "\n".join(lines) if lines else "  (none active)"
            else:
                cron_summary = "  (no jobs)"
        except Exception:
            cron_summary = "  (error)"

        period = "today" if days == 1 else f"last {days}d"
        text = (
            f"*Morning digest — {now.strftime('%Y-%m-%d %H:%M')} UTC*\n\n"
            f"*Sessions ({period}):*\n{sessions_summary}\n\n"
            f"*Top signals (latest):*\n{signals_summary}\n\n"
            f"*Skills built ({period}):*\n{skills_built}\n\n"
            f"*Cost today:* ${cost_today:.2f}\n\n"
            f"*Cron (next runs):*\n{cron_summary}"
        )

        if self.app and self.app.bot:
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=text, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=text)

        # Retro: mandatory reflection after morning digest
        try:
            import asyncio as _asyncio
            from ..retro import run_retro
            loop = _asyncio.get_running_loop()
            retro_text, retro_cost = await loop.run_in_executor(
                None,
                lambda: run_retro("digest", text,
                                  on_progress=lambda m: None,
                                  model="claude-sonnet-4-6")
            )
            retro_msg = f"*Retro*\n{retro_text}\n\n(${retro_cost:.3f})"
            if self.app and self.app.bot:
                for i in range(0, len(retro_msg), 4000):
                    try:
                        await self.app.bot.send_message(
                            chat_id=int(chat_id), text=retro_msg[i:i + 4000],
                            parse_mode="Markdown"
                        )
                    except Exception:
                        await self.app.bot.send_message(
                            chat_id=int(chat_id), text=retro_msg[i:i + 4000]
                        )
            if retro_cost > 0 and self._gateway:
                self._gateway._log_cost("telegram", "digest-retro", retro_cost)
        except Exception as e:
            log.warning(f"Retro after /digest failed (non-fatal): {e}")

    # ── /reflect — weekly self-analysis ─────────────────────────────

    async def _handle_reflect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run a weekly self-analysis: patterns, avoidance, next actions.

        Usage: /reflect [--days N] [--model X]
        """
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--days": {"type": "value", "cast": int, "default": 7},
            "--model": {"type": "value"},
        })
        days = max(1, min(flags["--days"], 30))
        model_override = flags["--model"]
        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        chat_id = str(update.message.chat_id)
        await update.message.reply_text(
            f"Reflecting on the last {days} days...\n~2-4 min."
        )

        loop = asyncio.get_running_loop()
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop)

        now = datetime.now(timezone.utc)
        since = (now - timedelta(days=days)).isoformat()

        reflect_prompt = (
            f"You are the REFLECT agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
            f"Run a {days}-day self-analysis. Do the following:\n\n"
            f"1. Query the SQLite DB at {EXODIR}/memory/sessions.db for sessions and messages "
            f"since {since}. Focus on:\n"
            f"   SELECT title, message_count, started_at FROM sessions WHERE started_at >= '{since}' "
            f"ORDER BY started_at DESC;\n"
            f"   SELECT role, content FROM messages WHERE timestamp >= '{since}' ORDER BY timestamp DESC LIMIT 100;\n\n"
            f"2. Check git log in ~/Desktop/projects/agenticEvolve for commits since {since[:10]}:\n"
            f"   git -C ~/Desktop/projects/agenticEvolve log --oneline --since={since[:10]}\n\n"
            f"3. List skills installed (ls ~/.claude/skills/) and when they were created.\n\n"
            f"4. Read ~/.agenticEvolve/memory/MEMORY.md and ~/.agenticEvolve/memory/USER.md.\n\n"
            f"5. Analyze and return:\n"
            f"   a) *Patterns I'm seeing* — what topics, tools, or workflows keep coming up?\n"
            f"   b) *What am I avoiding?* — what was deferred, blocked, or repeatedly postponed?\n"
            f"   c) *3 things to build next* — ranked by impact, based on patterns + gaps\n"
            f"   d) *System health* — any memory pressure, high cost, stale sessions, or skill bloat?\n\n"
            f"Return a concise, actionable report. No filler."
        )

        start_reporter()
        try:
            from ..agent import invoke_claude_streaming
            result = await loop.run_in_executor(
                None,
                lambda: invoke_claude_streaming(
                    reflect_prompt,
                    on_progress=on_progress_sync,
                    model=model,
                    session_context="[Reflect pipeline]",
                )
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Reflect error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Reflect failed: {e}")
            return
        finally:
            stop_reporter()

        response = result.get("text", "No output.")
        cost = result.get("cost", 0)
        tools_used = get_tool_count()

        header = f"*Reflect — last {days}d*\n({tools_used} steps, ${cost:.2f})\n\n"
        full = header + response
        for i in range(0, len(full), 4000):
            chunk = full[i:i+4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "reflect", cost)
