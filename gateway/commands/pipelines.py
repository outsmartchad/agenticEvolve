"""Pipeline command handlers (evolve, learn, absorb, gc) extracted as a mixin."""
import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"

try:
    from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class PipelineMixin:
    """Mixin providing pipeline command handlers.

    Expects the consuming class to provide (via multiple inheritance):
        self._gateway, self.app, self._is_allowed(), self._deny(),
        self._parse_flags(), self._make_progress_tracker(),
        self._resolve_reply_target(), self._get_lang_instruction()
    """

    async def _auto_sync_to_repo(self, pipeline: str):
        """Auto-commit and push changes to the git repo after a pipeline run."""
        import subprocess as sp
        repo_dir = Path.home() / "Desktop" / "projects" / "agenticEvolve"
        if not (repo_dir / ".git").exists():
            return

        try:
            # Sync skills from ~/.claude/skills/ to repo
            skills_src = Path.home() / ".claude" / "skills"
            skills_dst = repo_dir / "skills"
            if skills_src.exists():
                import shutil
                # Sync each skill dir
                for skill_dir in skills_src.iterdir():
                    if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                        dst = skills_dst / skill_dir.name
                        dst.mkdir(parents=True, exist_ok=True)
                        for f in skill_dir.iterdir():
                            if f.name.startswith("."):
                                continue
                            shutil.copy2(str(f), str(dst / f.name))

            # Sync gateway code
            gateway_src = Path.home() / ".agenticEvolve" / "gateway"
            gateway_dst = repo_dir / "gateway"
            if gateway_src.exists() and gateway_dst.exists():
                import shutil
                for f in gateway_src.glob("*.py"):
                    shutil.copy2(str(f), str(gateway_dst / f.name))
                platforms_src = gateway_src / "platforms"
                platforms_dst = gateway_dst / "platforms"
                if platforms_src.exists():
                    platforms_dst.mkdir(parents=True, exist_ok=True)
                    for f in platforms_src.glob("*.py"):
                        shutil.copy2(str(f), str(platforms_dst / f.name))

            # Git add, commit, push
            sp.run(["git", "add", "-A"], cwd=str(repo_dir), capture_output=True, timeout=30)
            diff = sp.run(["git", "diff", "--cached", "--stat"], cwd=str(repo_dir), capture_output=True, text=True, timeout=10)
            if diff.stdout.strip():
                sp.run(
                    ["git", "commit", "-m", f"auto: sync after /{pipeline} pipeline"],
                    cwd=str(repo_dir), capture_output=True, timeout=30
                )
                sp.run(["git", "push"], cwd=str(repo_dir), capture_output=True, timeout=60)
                log.info(f"Auto-synced to repo after /{pipeline}")
            else:
                log.info(f"No changes to sync after /{pipeline}")
        except Exception as e:
            log.error(f"Auto-sync failed after /{pipeline}: {e}")

    async def _security_prescan_github(self, target: str, chat_id: str, loop) -> bool:
        """Clone a GitHub repo and run security scan. Returns True if blocked."""
        import subprocess as sp
        from ..security import scan_directory, format_telegram_report

        scan_path = Path("/tmp/learn-scan")

        # Clone
        try:
            sp.run(["rm", "-rf", str(scan_path)], capture_output=True, timeout=10)
            proc = sp.run(
                ["git", "clone", "--depth", "1", target, str(scan_path)],
                capture_output=True, text=True, timeout=120
            )
            if proc.returncode != 0:
                # Clone failed — let claude -p handle it
                return False
        except Exception:
            return False

        # Security scan
        result = scan_directory(scan_path, label=target)
        report = format_telegram_report(result)

        if result.verdict == "BLOCKED":
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id),
                    text=report + "\n\n/learn aborted for safety.",
                )
            except Exception:
                pass
            # Clean up
            sp.run(["rm", "-rf", str(scan_path)], capture_output=True, timeout=10)
            return True

        if result.verdict == "WARNING":
            try:
                await self.app.bot.send_message(chat_id=int(chat_id), text=report)
            except Exception:
                pass

        return False

    async def _handle_evolve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run multi-stage evolve pipeline with live progress."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
            "--skip-security-scan": {"type": "bool"},
            "--model": {"type": "value"},
        })
        dry_run = flags["--dry-run"]
        skip_security_scan = flags["--skip-security-scan"]
        model_override = flags["--model"]

        chat_id = str(update.message.chat_id)
        if dry_run:
            await update.message.reply_text(
                "Dry run: COLLECT → ANALYZE (stops before building)\n"
                "~2-4 min",
            )
        else:
            await update.message.reply_text(
                "Evolving... COLLECT → ANALYZE → BUILD → REVIEW → REPORT\n"
                "~5-10 min. Progress below.",
            )

        loop = asyncio.get_running_loop()
        _stages = ["collect", "analyze"] if dry_run else ["collect", "analyze", "build", "review", "report"]
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop, pipeline_stages=_stages)

        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        start_reporter()
        try:
            from ..evolve import EvolveOrchestrator

            orchestrator = EvolveOrchestrator(
                model=model,
                on_progress=on_progress_sync,
                skip_security_scan=skip_security_scan,
            )

            summary, cost = await loop.run_in_executor(
                None, lambda: orchestrator.run(dry_run=dry_run)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Evolve error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Evolution failed: {e}")
            return
        finally:
            stop_reporter()

        # Send single comprehensive report
        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_summary = summary + footer
        for i in range(0, len(full_summary), 4000):
            chunk = full_summary[i:i+4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk
                )

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "evolve", cost)

        # Auto-commit and push new skills to git repo
        await self._auto_sync_to_repo("evolve")

    async def _handle_learn(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deep-dive a repo, library, or tech. Analyze how we benefit and optionally build a skill."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--skip-security-scan": {"type": "bool"},
            "--model": {"type": "value"},
            "--dry-run": {"aliases": ["dry-run", "preview"], "type": "bool"},
        })
        skip_security_scan = flags["--skip-security-scan"]
        model_override = flags["--model"]
        dry_run = flags["--dry-run"]

        target = self._resolve_reply_target(" ".join(raw_args), update)
        if not target:
            await update.message.reply_text(
                "*Usage:* `/learn <repo-url or tech name>`\n\n"
                "*Options:*\n"
                "`--dry-run` — security scan + preview only, no full analysis\n"
                "`--model <name>` — override model (e.g. opus for deeper analysis)\n"
                "`--skip-security-scan` — bypass security check\n\n"
                "*Examples:*\n"
                "`/learn https://github.com/vercel/ai`\n"
                "`/learn --model opus anthropic tool-use patterns`\n"
                "`/learn --dry-run https://github.com/nicepkg/aide`\n\n"
                "Tip: Reply to a message containing a URL and just send `/learn`",
                parse_mode="Markdown"
            )
            return

        short_target = target[:60] + ("..." if len(target) > 60 else "")
        if dry_run:
            await update.message.reply_text(
                f"Learning (preview): {short_target}\n~1-2 min. Security scan only.",
            )
        else:
            await update.message.reply_text(
                f"Learning: {short_target}\n~3-6 min. Progress below.",
            )

        chat_id = str(update.message.chat_id)
        user_id = str(update.message.from_user.id)
        loop = asyncio.get_running_loop()

        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop, pipeline_stages=["fetch", "analyze", "extract"])

        is_url = target.startswith("http://") or target.startswith("https://")
        is_github = "github.com" in target

        # Common context about our system for the learn agent
        system_context = (
            f"You are the LEARN agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
            f"Our system: Python asyncio gateway → Claude Code (claude -p) → Telegram. "
            f"Bounded memory (MEMORY.md/USER.md), SQLite+FTS5 sessions, agent-managed cron, "
            f"skills in ~/.claude/skills/, safety-gated skill queue.\n\n"
            f"Vincent builds AI agents, onchain infrastructure, and developer tools. "
            f"Stack: TypeScript/React frontends, Python for infra/agents.\n\n"
        )

        # The core of /learn: extract patterns, evaluate operational benefit
        analysis_instructions = (
            f"EXTRACT PATTERNS:\n"
            f"- What design patterns, architectural decisions, or techniques does this use?\n"
            f"- What can we steal and apply to our own system — even if we don't use this tool directly?\n"
            f"- Are there code patterns that would improve our gateway, memory system, cron, or agent invocation?\n\n"
            f"EVALUATE OPERATIONAL BENEFIT:\n"
            f"- Does this solve a real problem we have right now? Be specific.\n"
            f"- Would adopting this speed up our development workflow or make our agent system more capable?\n"
            f"- What's the cost/effort vs benefit? Is it worth the integration work?\n"
            f"- Verdict: ADOPT (use it) / STEAL (take patterns, skip the dep) / SKIP (not useful for us)\n\n"
            f"IF VERDICT IS ADOPT OR STEAL:\n"
            f"- Create a skill directly in ~/.claude/skills/<name>/SKILL.md with concrete instructions\n"
            f"- Include a Source: <url> line at the bottom of the SKILL.md\n"
            f"- Install it directly — no queue, no approval needed\n\n"
            f"MEMORY UPDATE:\n"
            f"- Add a concise entry about what we learned to ~/.agenticEvolve/memory/MEMORY.md\n"
            f"- Focus on the extractable pattern, not a description of the tool\n"
            f"- Use § as separator, respect the 2200 char limit\n\n"
            f"STRUCTURED OUTPUT (REQUIRED):\n"
            f"At the END of your response, include this JSON block so we can store the learning:\n"
            f"```json\n"
            f'{{"verdict": "ADOPT|STEAL|SKIP", '
            f'"patterns": "key patterns extracted (1-3 sentences)", '
            f'"operational_benefit": "how this helps our system (1-2 sentences)", '
            f'"skill_created": "skill-name or empty string"}}\n'
            f"```\n\n"
        )

        # Security scan for GitHub repos: clone first, scan, then proceed
        if is_github and not skip_security_scan:
            self._report_sync = on_progress_sync
            security_blocked = await self._security_prescan_github(target, chat_id, loop)
            if security_blocked:
                return
        elif is_github and skip_security_scan:
            on_progress_sync("*Security scan: skipped (--skip-security-scan)*")

        if is_github:
            learn_prompt = (
                system_context +
                f"Deep-dive this GitHub repo: {target}\n\n"
                f"The repo has been pre-cloned to /tmp/learn-scan/ and passed security scan.\n"
                f"1. Read the repo from /tmp/learn-scan/\n"
                f"2. Read the README, key source files, and architecture\n"
                f"3. Understand how it works — focus on the interesting engineering, not surface features\n\n"
                f"SECURITY: Do NOT run any install scripts, build commands, or execute code from this repo. "
                f"READ ONLY. Do not run npm install, pip install, make, or any setup scripts.\n\n"
                + analysis_instructions +
                f"Return: patterns extracted, operational verdict, and any skill/memory updates made."
            )
        elif is_url:
            learn_prompt = (
                system_context +
                f"Research this URL: {target}\n\n"
                f"1. Fetch the page content using WebFetch\n"
                f"2. Find the source repo if it exists\n"
                f"3. Understand the core idea and how it's implemented\n\n"
                + analysis_instructions +
                f"Return: patterns extracted, operational verdict, and any skill/memory updates made."
            )
        else:
            learn_prompt = (
                system_context +
                f"Research this technology/concept: {target}\n\n"
                f"1. Search the web for '{target}' — find the repo, docs, key resources\n"
                f"2. Understand how it works and what problem it solves\n"
                f"3. Look at the source code if available — the patterns matter more than the docs\n\n"
                + analysis_instructions +
                f"Return: patterns extracted, operational verdict, and any skill/memory updates made."
            )

        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        # Inject language preference into prompt
        lang_instruction = self._get_lang_instruction(user_id)
        if lang_instruction:
            learn_prompt += lang_instruction

        # Dry run: show security scan result and what would be analyzed, then stop
        if dry_run:
            lines = [f"*Learn dry run: {target}*\n"]
            lines.append(f"Type: {'GitHub repo' if is_github else 'URL' if is_url else 'topic'}")
            lines.append(f"Model: {model}")
            lines.append(f"Security scan: {'skipped' if skip_security_scan else 'passed'}")
            lines.append(f"\nWould run full analysis with Claude ({model}).")
            lines.append(f"Run `/learn {target}` to execute.")
            await self.app.bot.send_message(chat_id=int(chat_id), text="\n".join(lines))
            return

        start_reporter()
        try:
            from ..agent import invoke_claude_streaming

            result = await loop.run_in_executor(
                None,
                lambda: invoke_claude_streaming(
                    learn_prompt,
                    on_progress=on_progress_sync,
                    model=model,
                    session_context=f"[Learn: {target[:50]}]"
                )
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Learn error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Learn failed: {e}")
            return
        finally:
            stop_reporter()

        response = result.get("text", "No output.")
        cost = result.get("cost", 0)
        tools_used = get_tool_count()

        # Send single comprehensive report
        header = f"*Learn: {target}*\n({tools_used} steps, ${cost:.2f})\n\n"
        full = header + response
        for i in range(0, len(full), 4000):
            chunk = full[i:i+4000]
            try:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk, parse_mode="Markdown")
            except Exception:
                await self.app.bot.send_message(chat_id=int(chat_id), text=chunk)

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "learn", cost)

        # Auto-sync to repo
        await self._auto_sync_to_repo("learn")

        # Store learning in DB
        try:
            from ..session_db import add_learning
            learning_data = {"verdict": "UNKNOWN", "patterns": "", "operational_benefit": "", "skill_created": ""}
            json_start = response.rfind('```json')
            json_end = response.rfind('```', json_start + 7) if json_start >= 0 else -1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start + 7:json_end].strip()
                try:
                    learning_data = json.loads(json_str)
                except (json.JSONDecodeError, ValueError):
                    pass

            target_type = "github" if is_github else ("url" if is_url else "topic")
            add_learning(
                target=target,
                target_type=target_type,
                verdict=learning_data.get("verdict", "UNKNOWN"),
                patterns=learning_data.get("patterns", ""),
                operational_benefit=learning_data.get("operational_benefit", ""),
                skill_created=learning_data.get("skill_created", ""),
                full_report=response[:8000],
                cost=cost,
            )
            log.info(f"[learn] Stored learning: {target} -> {learning_data.get('verdict', '?')}")
        except Exception as e:
            log.warning(f"[learn] Failed to store learning: {e}")

    async def _handle_absorb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deep scan a target, analyze gaps in our system, and implement improvements."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {
            "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
            "--skip-security-scan": {"type": "bool"},
            "--model": {"type": "value"},
        })
        dry_run = flags["--dry-run"]
        skip_security_scan = flags["--skip-security-scan"]
        model_override = flags["--model"]

        target = self._resolve_reply_target(" ".join(raw_args), update)
        if not target:
            await update.message.reply_text(
                "*Usage:* `/absorb <repo-url or tech/architecture>`\n\n"
                "*Options:*\n"
                "`--dry-run` — scan + gap analysis only\n"
                "`--model <name>` — override model for this run\n"
                "`--skip-security-scan` — bypass security check\n\n"
                "*Examples:*\n"
                "`/absorb https://github.com/NousResearch/hermes-agent`\n"
                "`/absorb --model opus persistent memory protocol`\n"
                "`/absorb --dry-run https://github.com/langchain-ai/langgraph`\n\n"
                "Tip: Reply to a message containing a URL and just send `/absorb`",
                parse_mode="Markdown"
            )
            return

        is_wechat = target.lower().startswith("wechat")
        is_url = target.startswith("http://") or target.startswith("https://")
        is_github = "github.com" in target
        target_type = "wechat" if is_wechat else ("github" if is_github else ("url" if is_url else "topic"))

        short_target = target[:60] + ("..." if len(target) > 60 else "")
        if dry_run:
            await update.message.reply_text(
                f"Absorb (dry run): {short_target}\n"
                f"SCAN → GAP (stops before implementing)\n~3-5 min. Progress below.",
            )
        else:
            await update.message.reply_text(
                f"Absorbing: {short_target}\n"
                f"SCAN → GAP → PLAN → IMPLEMENT → REPORT\n~8-15 min. Progress below.",
            )

        chat_id = str(update.message.chat_id)
        loop = asyncio.get_running_loop()

        _absorb_stages = ["scan", "gap"] if dry_run else ["scan", "gap", "plan", "implement", "report"]
        on_progress_sync, get_tool_count, start_reporter, stop_reporter = \
            self._make_progress_tracker(chat_id, loop, pipeline_stages=_absorb_stages)

        model = model_override or (self._gateway.config.get("model", "sonnet") if self._gateway else "sonnet")

        # Security prescan for GitHub repos (Layer 1 — before handing to absorb pipeline)
        is_github = target.startswith("https://github.com/") or target.startswith("git@github.com:")
        if is_github and not skip_security_scan and not is_wechat:
            security_blocked = await self._security_prescan_github(target, chat_id, asyncio.get_running_loop())
            if security_blocked:
                return
        elif is_github and skip_security_scan:
            on_progress_sync("*Security scan: skipped (--skip-security-scan)*")

        start_reporter()
        try:
            from ..absorb import AbsorbOrchestrator

            orchestrator = AbsorbOrchestrator(
                target=target,
                target_type=target_type,
                model=model,
                on_progress=on_progress_sync,
                skip_security_scan=skip_security_scan,
            )

            summary, cost = await loop.run_in_executor(
                None, lambda: orchestrator.run(dry_run=dry_run)
            )
        except Exception as e:
            stop_reporter()
            log.error(f"Absorb error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"Absorb failed: {e}")
            return
        finally:
            stop_reporter()

        # Send single comprehensive report
        tools_used = get_tool_count()
        footer = f"\n\n({tools_used} steps, ${cost:.2f})"
        full_summary = summary + footer
        for i in range(0, len(full_summary), 4000):
            chunk = full_summary[i:i+4000]
            try:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk, parse_mode="Markdown"
                )
            except Exception:
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=chunk
                )

        if cost > 0 and self._gateway:
            self._gateway._log_cost("telegram", "absorb", cost)

        # Auto-sync to repo
        await self._auto_sync_to_repo("absorb")

        # Store in learnings DB
        try:
            from ..session_db import add_learning
            add_learning(
                target=target,
                target_type=target_type,
                verdict="ABSORBED",
                patterns=f"Absorbed via 5-stage pipeline. See full report.",
                operational_benefit=f"System improvements implemented. Cost: ${cost:.2f}",
                skill_created="",
                full_report=summary[:8000],
                cost=cost,
            )
        except Exception as e:
            log.warning(f"[absorb] Failed to store learning: {e}")

    async def _handle_gc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run garbage collection — clean stale sessions, orphan skills, check memory health."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"}})
        dry_run = flags["--dry-run"]

        mode = "preview" if dry_run else "cleanup"
        await update.message.reply_text(f"Running GC ({mode})...", parse_mode="Markdown")

        chat_id = str(update.message.chat_id)
        loop = asyncio.get_running_loop()

        try:
            from ..gc import run_gc, format_gc_report

            report = await loop.run_in_executor(None, lambda: run_gc(dry_run=dry_run))
            text = format_gc_report(report)

            for i in range(0, len(text), 4000):
                await self.app.bot.send_message(
                    chat_id=int(chat_id), text=text[i:i+4000], parse_mode="Markdown"
                )
        except Exception as e:
            log.error(f"GC error: {e}")
            await self.app.bot.send_message(chat_id=int(chat_id), text=f"GC failed: {e}")
