"""Misc command handlers mixin — extracted from TelegramAdapter."""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class MiscMixin:

    def _extract_urls(self, text: str) -> list[str]:
        """Extract meaningful URLs from text (not just any link)."""
        return self._URL_RE.findall(text)

    async def _offer_absorb_learn(self, update: Update, target: str, target_type: str = "link"):
        """Show inline keyboard asking user if they want to absorb/learn a target."""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Absorb", callback_data=f"absorb:{target[:200]}"),
                InlineKeyboardButton("Learn", callback_data=f"learn:{target[:200]}"),
            ],
            [
                InlineKeyboardButton("Just chat", callback_data="chat:proceed"),
            ]
        ])
        await update.message.reply_text(
            f"I noticed a {target_type}. Want me to absorb it into our system or learn from it?\n\n"
            f"{target[:200]}",
            reply_markup=keyboard
        )

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses for absorb/learn prompts."""
        query = update.callback_query
        if not query or not query.data:
            return
        await query.answer()

        user_id = query.from_user.id
        if not self._is_allowed(user_id):
            return

        chat_id = str(query.message.chat_id)
        data = query.data

        if data.startswith("absorb:"):
            target = data[7:]
            await query.edit_message_text(f"Absorbing: {target[:100]}...")

            is_url = target.startswith("http://") or target.startswith("https://")
            is_github = "github.com" in target
            target_type = "github" if is_github else ("url" if is_url else "topic")
            model = self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet"

            try:
                from ..absorb import AbsorbOrchestrator

                loop = asyncio.get_running_loop()
                on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
                    self._make_progress_tracker(chat_id, loop)

                orchestrator = AbsorbOrchestrator(
                    target=target,
                    target_type=target_type,
                    model=model,
                    on_progress=on_progress_sync,
                )

                start_reporter()
                try:
                    summary, cost = await loop.run_in_executor(
                        None, lambda: orchestrator.run(dry_run=False)
                    )
                finally:
                    stop_reporter()

                tools_used = get_tool_count()
                footer = f"\n\n({tools_used} steps, ${cost:.2f})"
                full_summary = summary + footer
                for i in range(0, len(full_summary), 4000):
                    await self.app.bot.send_message(chat_id=int(chat_id), text=full_summary[i:i+4000])

                try:
                    from ..session_db import add_learning
                    add_learning(
                        target=target, target_type=target_type,
                        verdict="ABSORBED",
                        patterns="Absorbed via inline button. See full report.",
                        operational_benefit=f"System improvements implemented. Cost: ${cost:.2f}",
                        skill_created="", full_report=summary[:8000], cost=cost,
                    )
                except Exception as e:
                    log.warning(f"Failed to store absorb learning: {e}")

            except Exception as e:
                log.error(f"Callback absorb error: {e}")
                await self.app.bot.send_message(chat_id=int(chat_id), text=f"Absorb failed: {e}")

        elif data.startswith("learn:"):
            target = data[6:]
            await query.edit_message_text(f"Learning from: {target[:100]}...")

            is_url = target.startswith("http://") or target.startswith("https://")
            is_github = "github.com" in target
            target_type = "github" if is_github else ("url" if is_url else "topic")
            model = self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet"

            # Security prescan for GitHub repos
            if is_github:
                security_blocked = await self._security_prescan_github(target, chat_id, asyncio.get_running_loop())
                if security_blocked:
                    return

            try:
                from ..agent import invoke_claude_streaming, build_system_prompt

                clone_note = ""
                if is_github:
                    clone_note = (
                        f"The repo has been pre-cloned to /tmp/learn-scan/ and passed security scan.\n"
                        f"Read from /tmp/learn-scan/ instead of cloning again.\n"
                        f"SECURITY: Do NOT run install scripts, build commands, or execute any code from this repo.\n\n"
                    )

                prompt = (
                    f"Deep-dive this target and extract patterns our system can learn from:\n\n"
                    f"Target: {target}\n\n"
                    f"{clone_note}"
                    f"Focus on: what patterns can we steal, what would benefit our development workflow, "
                    f"and whether we should ADOPT (use it) / STEAL (take patterns, skip dep) / SKIP (not useful).\n\n"
                    f"At the END return a JSON block:\n"
                    f'```json\n{{"verdict": "ADOPT|STEAL|SKIP", "patterns": "...", '
                    f'"operational_benefit": "...", "skill_created": ""}}\n```'
                )

                loop = asyncio.get_running_loop()

                def _run_learn():
                    return invoke_claude_streaming(
                        message=prompt,
                        on_progress=lambda x: None,
                        model=model,
                    )

                result = await loop.run_in_executor(None, _run_learn)

                response = result.get("text", "No response")
                cost = result.get("cost", 0)
                for i in range(0, len(response), 4000):
                    await self.app.bot.send_message(chat_id=int(chat_id), text=response[i:i+4000])

                # Store learning
                try:
                    from ..session_db import add_learning
                    learning_data = {}
                    if "```json" in response:
                        json_start = response.find("```json")
                        json_end = response.find("```", json_start + 7) if json_start >= 0 else -1
                        json_str = response[json_start + 7:json_end].strip()
                        try:
                            learning_data = json.loads(json_str)
                        except (json.JSONDecodeError, ValueError):
                            pass

                    add_learning(
                        target=target, target_type=target_type,
                        verdict=learning_data.get("verdict", "UNKNOWN"),
                        patterns=learning_data.get("patterns", ""),
                        operational_benefit=learning_data.get("operational_benefit", ""),
                        skill_created=learning_data.get("skill_created", ""),
                        full_report=response[:8000], cost=cost,
                    )
                except Exception as e:
                    log.warning(f"Failed to store learning from callback: {e}")

            except Exception as e:
                log.error(f"Callback learn error: {e}")
                await self.app.bot.send_message(chat_id=int(chat_id), text=f"Learn failed: {e}")

        elif data == "chat:proceed":
            await query.edit_message_text("Got it, continuing as normal chat.")

    async def _handle_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restart the gateway process remotely via Telegram."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        await update.message.reply_text("Restarting gateway in 2s...")

        # Write a restart script to /tmp, then execute it detached.
        # This avoids pkill matching the script's own command line.
        import subprocess as sp
        restart_sh = Path("/tmp/ae-restart.sh")
        restart_sh.write_text(
            "#!/bin/bash\n"
            "sleep 2\n"
            "# Kill gateway by PID file or process match\n"
            "PID=$(pgrep -f 'python3 -m gateway.run')\n"
            "if [ -n \"$PID\" ]; then kill -9 $PID; fi\n"
            "sleep 1\n"
            "cd ~/.agenticEvolve\n"
            "nohup python3 -m gateway.run > /dev/null 2>&1 &\n"
        )
        restart_sh.chmod(0o755)
        sp.Popen(
            [str(restart_sh)],
            start_new_session=True,
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )

    async def _handle_do(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Parse natural language into a structured command, then execute it in background."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--preview": {"aliases": ["--dry-run"], "type": "bool"}})
        preview = flags["--preview"]
        text = " ".join(raw_args)

        # Resolve reply context — inject URLs if user said "this"/"that"/"it"
        reply_text, reply_urls = self._get_reply_context(update)
        text = self._resolve_reply_target(text, update)
        reply_context = reply_text

        if not text:
            await update.message.reply_text(
                "*Usage:* `/do <natural language instruction>`\n\n"
                "*Options:*\n"
                "`--preview` — show parsed command without running it\n\n"
                "*Examples:*\n"
                "`/do absorb this repo https://github.com/foo/bar and skip the security scan`\n"
                "`/do learn about htmx`\n"
                "`/do --preview study this repo https://github.com/vercel/ai`\n"
                "`/do search for memory management in past sessions`\n"
                "`/do show me the cost so far`\n"
                "`/do schedule absorb langchain every day at 9am`\n\n"
                "I'll parse your intent, show the mapped command, and run it.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text("Parsing intent...")

        intent = await self._parse_intent(text, reply_context=reply_context)
        if not intent:
            await update.message.reply_text(
                "Couldn't map that to a known command. Try rephrasing, or use a command directly.\n\n"
                "Send `/help` for available commands."
            )
            return

        cmd = intent["command"]
        confidence = intent.get("confidence", 0)

        if preview:
            await update.message.reply_text(
                f"*Preview (not executed):*\n`{cmd}` (confidence: {confidence:.0%})\n\n"
                f"Run `/do {text}` without --preview to execute.",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text(
            f"Parsed: `{cmd}` (confidence: {confidence:.0%})\nRunning..."
        )
        await self._run_command_background(update, context, cmd)

    # ── Intent parser (natural language → command) ─────────────────

    # Commands the intent parser knows about
    _COMMAND_SCHEMA = """Available commands:
/absorb <repo-url or topic> [--dry-run] [--model <name>] [--skip-security-scan]
  Absorb patterns from a repo/topic into our system.
/learn <repo-url or topic> [--dry-run] [--model <name>] [--skip-security-scan]
  Deep-dive a repo/tech, extract patterns, evaluate benefit.
/evolve [--dry-run] [--model <name>] [--skip-security-scan]
  Run the evolution pipeline (collect signals, build skills).
/search <query> [--limit <n>]
  Full-text search across past sessions.
/sessions [--limit <n>]
  List recent sessions.
/newsession [title]
  Start a fresh session, optionally with a title.
/memory
  View bounded memory.
/cost [--week]
  View cost usage. Add --week for weekly total.
/status
  System status.
/skills
  List installed skills.
/learnings [query] [--limit <n>]
  List or search stored learnings.
/model <name>
  Switch model (e.g. sonnet, opus, haiku).
/produce [--ideas N] [--model <name>]
  Brainstorm business/app ideas from all collected signals.
/wechat [--hours N] [--model <name>]
  Summarize recent WeChat group chat messages.
/digest [--days N]
  Morning briefing (sessions, signals, skills, cost).
/gc [--dry-run]
  Run garbage collection.
/loop <interval> <prompt> [--model <name>] [--max-runs <n>] [--start-now]
  Schedule a recurring command.
/loops
  List scheduled loops.
/unloop <id>
  Remove a scheduled loop.
/pause <id|--all>
  Pause a scheduled loop or all loops.
/unpause <id|--all>
  Unpause a scheduled loop or all loops.
/queue
  List skills pending approval.
/approve <name> [--force]
  Approve a queued skill.
/reject <name>
  Reject a queued skill.
/soul
  View SOUL.md personality.
/config
  View runtime config.
/heartbeat
  Check if gateway is alive.
/notify <duration> <message>
  Set a one-time reminder.
/help
  Show help.
"""

    async def _parse_intent(self, text: str, reply_context: str = "") -> dict | None:
        """Parse natural language into a structured command using a lightweight Claude call.

        Returns dict with {command, display} or None if no command matched.
        """
        import subprocess as sp

        reply_section = ""
        if reply_context:
            reply_section = (
                f"\nThe user is REPLYING to this previous message (use it to resolve 'this', 'that', 'it', etc.):\n"
                f"---\n{reply_context[:1500]}\n---\n\n"
            )

        prompt = (
            "You are a command parser. The user sent a natural language message to an AI agent system.\n"
            "Your job: determine if this message maps to one of the available commands below.\n\n"
            f"{self._COMMAND_SCHEMA}\n"
            f"{reply_section}"
            "Rules:\n"
            "- If the message clearly maps to a command, return the exact command string.\n"
            "- If the message is general chat/question NOT related to any command, return null.\n"
            "- Preserve URLs and arguments exactly as the user provided them.\n"
            "- If the user says 'this', 'that', 'it' and there is a replied-to message with a URL, use that URL as the target.\n"
            "- Map synonyms: 'study'/'research'/'dive into' → /learn, 'integrate'/'absorb'/'steal from' → /absorb, "
            "'scan'/'evolve'/'find new tools' → /evolve, 'find'/'search for' → /search\n"
            "- Map flags from natural language: 'skip security'/'no security scan'/'skip scan' → --skip-security-scan, "
            "'preview'/'just check'/'dry run' → --dry-run\n\n"
            "Return ONLY a JSON object, nothing else:\n"
            '{"command": "/absorb https://... --skip-security-scan", "confidence": 0.95}\n'
            'or\n'
            '{"command": null, "confidence": 0.0}\n\n'
            f"User message: {text}"
        )

        try:
            proc = sp.run(
                ["claude", "-p", "--model", "haiku", prompt],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return None

            output = proc.stdout.strip()
            # Extract JSON from response
            start = output.find("{")
            end = output.rfind("}") + 1
            if start < 0 or end <= start:
                return None

            parsed = json.loads(output[start:end])
            cmd = parsed.get("command")
            confidence = parsed.get("confidence", 0)

            if not cmd or confidence < 0.7:
                return None

            return {"command": cmd, "display": cmd, "confidence": confidence}

        except Exception as e:
            log.warning(f"Intent parse failed: {e}")
            return None
