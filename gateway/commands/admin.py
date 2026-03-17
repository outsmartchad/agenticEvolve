"""Admin command handlers mixin — extracted from TelegramAdapter."""
from __future__ import annotations
import json
import logging
from pathlib import Path

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


class AdminMixin:

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)
        await update.message.reply_text(
            "agenticEvolve connected.\n\n"
            "Send me any message and I'll process it with Claude Code.\n"
            "Use /help to see available commands."
        )

    # ── /help ────────────────────────────────────────────────────

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)
        await update.message.reply_text(
            "agenticEvolve commands\n\n"
            "Core\n"
            "/help — Show this help\n"
            "/status — System status\n"
            "/model [name] — View or switch model\n"
            "/cost [--week] — Today's cost (add --week for weekly)\n"
            "/config — View runtime config\n"
            "/heartbeat — Check if bot is alive\n\n"
            "Sessions\n"
            "/newsession [title] — Start new session (optionally named)\n"
            "/sessions [--limit N] — Recent sessions\n"
            "/search <query> [--limit N] — FTS5 search past sessions\n\n"
            "Memory & Identity\n"
            "/memory — Show bounded memory\n"
            "/soul — View agent personality\n\n"
            "Evolution\n"
            "/evolve [--dry-run] [--model X] [--skip-security-scan]\n"
            "/absorb <target> [--dry-run] [--model X] [--skip-security-scan]\n"
            "/learn <target> [--dry-run] [--model X] [--skip-security-scan]\n"
            "/learnings [query] [--limit N] — View past findings\n\n"
            "Skills\n"
            "/skills — List installed skills\n"
            "/queue — Skills pending approval\n"
            "/approve <name> [--force] — Install a queued skill\n"
            "/reject <name> [reason] — Remove a queued skill\n"
            "/scanskills — AgentShield security scan of all installed skills\n\n"
            "Scheduling\n"
            "/loop <interval> <prompt> [--model X] [--max-runs N] [--start-now]\n"
            "/loops — List active loops\n"
            "/unloop <id> — Cancel a loop\n"
            "/pause <id|--all> — Pause loop(s)\n"
            "/unpause <id|--all> — Resume loop(s)\n"
            "/notify <delay> <msg> — One-shot reminder\n\n"
            "Voice\n"
            "/speak <text> [--voice <name>] — Text-to-speech\n"
            "/speak --voices [lang] — List available voices\n"
            "/speak --mode <off|always|inbound> — Auto-TTS mode\n"
            "Send a voice message — auto-transcribe + reply\n\n"
            "Ideas\n"
            "/produce [--ideas N] [--model X] — Brainstorm business ideas from all signals\n\n"
            "Platform Digests\n"
            "/wechat [--hours N] [--model X] — WeChat group chat digest\n"
            "/discord [--hours N] [--model X] — Discord channel digest (subscribed)\n"
            "/whatsapp — WhatsApp digest (coming soon)\n"
            "/absorb wechat [--hours N] — Deep absorb from group chats\n\n"
            "Monitoring\n"
            "/subscribe — Select channels/users to monitor for digests\n"
            "/serve — Select channels/users for the agent to actively respond in\n\n"
            "Briefings\n"
            "/digest [--days N] — Morning briefing\n\n"
            "Identity\n"
            "/link <platform> <platform_user_id> [display_name] — Link cross-platform identity\n"
            "/whoami — Show linked identities for your account\n\n"
            "Background Tasks\n"
            "/tasks — List running/recent background tasks\n"
            "/cancel <task_id> — Cancel a running task\n"
            "/hooks — Show registered hook listeners\n\n"
            "Configuration\n"
            "/reload — Force-reload config.yaml with validation\n"
            "/allowlist — Manage exec mode command allowlist\n\n"
            "Maintenance\n"
            "/gc [--dry-run] — Garbage collection\n\n"
            "Settings\n"
            "/lang [code] — Set output language (zh, en, ja, ko, ...)\n\n"
            "Natural Language\n"
            "/do <instruction> [--preview] — Parse intent + run command\n\n"
            "Or just send any message to chat with Claude."
        )

    # ── /status ──────────────────────────────────────────────────

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..agent import get_today_cost
        from ..session_db import stats

        s = stats()
        today_cost = get_today_cost()
        mem_path = EXODIR / "memory" / "MEMORY.md"
        user_path = EXODIR / "memory" / "USER.md"
        mem_chars = len(mem_path.read_text()) if mem_path.exists() else 0
        user_chars = len(user_path.read_text()) if user_path.exists() else 0

        # Count skills
        skills_dir = Path.home() / ".claude" / "skills"
        skill_count = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.exists() else 0

        # Count cron jobs
        active_jobs = 0
        if CRON_JOBS_FILE.exists():
            try:
                jobs = json.loads(CRON_JOBS_FILE.read_text())
                active_jobs = sum(1 for j in jobs if not j.get("paused", False))
            except Exception:
                pass

        # Autonomy status (ZeroClaw pattern)
        from ..autonomy import format_autonomy_status
        gw = self._gateway
        cfg = gw.config if gw else {}
        autonomy_info = format_autonomy_status(cfg) if cfg else "Autonomy: unknown"

        current_model = cfg.get("model", "sonnet") if cfg else "sonnet"

        text = (
            f"*agenticEvolve status*\n\n"
            f"Gateway: running\n"
            f"Model: {current_model}\n"
            f"Memory: {mem_chars}/2200 chars\n"
            f"User profile: {user_chars}/1375 chars\n"
            f"Sessions: {s['total_sessions']} total, {s['total_messages']} msgs\n"
            f"Skills: {skill_count} installed\n"
            f"Cron jobs: {active_jobs} active\n"
            f"DB: {s['db_size_mb']} MB\n"
            f"Cost today: ${today_cost:.2f}\n\n"
            f"{autonomy_info}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    # ── /memory ──────────────────────────────────────────────────

    async def _handle_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        mem_path = EXODIR / "memory" / "MEMORY.md"
        user_path = EXODIR / "memory" / "USER.md"
        mem = mem_path.read_text().strip() if mem_path.exists() else "(empty)"
        user = user_path.read_text().strip() if user_path.exists() else "(empty)"

        text = (
            f"MEMORY.md ({len(mem)}/2200)\n\n{mem}\n\n"
            f"---\n\n"
            f"USER.md ({len(user)}/1375)\n\n{user}"
        )
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /sessions ────────────────────────────────────────────────

    async def _handle_sessions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--limit": {"type": "value", "cast": int, "default": 10}})
        limit = min(flags["--limit"], 50)

        from ..session_db import list_sessions
        rows = list_sessions(limit=limit)
        if not rows:
            return await update.message.reply_text("No sessions yet.")

        lines = ["*Recent sessions*\n"]
        for r in rows:
            title = r.get("title") or "(untitled)"
            msgs = r.get("message_count", 0)
            src = r.get("source", "?")
            ts = r.get("started_at", "?")[:16]
            lines.append(f"`{ts}` {src} — {title} ({msgs} msgs)")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── /newsession ──────────────────────────────────────────────

    async def _handle_newsession(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        title = " ".join(context.args) if context.args else ""
        if not title:
            reply_text, _ = self._get_reply_context(update)
            if reply_text:
                title = reply_text[:100]

        chat_id = str(update.message.chat_id)
        key = f"telegram:{chat_id}"
        if self._gateway:
            sid = self._gateway._active_sessions.pop(key, None)
            self._gateway._session_last_active.pop(key, None)
            self._gateway._session_msg_count.pop(key, None)
            self._gateway._locks.pop(key, None)
            if sid:
                from ..session_db import end_session, set_title
                end_session(sid)
            # If title provided, pre-create a titled session
            if title:
                from ..session_db import create_session, generate_session_id
                new_sid = create_session(generate_session_id(), "telegram", chat_id)
                set_title(new_sid, title)
                self._gateway._active_sessions[key] = new_sid
        msg = f"New session started: *{title}*" if title else "New session started. Send your next message."
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ── /cost ────────────────────────────────────────────────────

    async def _handle_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--week": {"type": "bool"}})

        from ..agent import get_today_cost, get_week_cost
        today_cost = get_today_cost()
        daily_cap = 5.0
        weekly_cap = 25.0
        if self._gateway:
            daily_cap = self._gateway.config.get("daily_cost_cap", 5.0)
            weekly_cap = self._gateway.config.get("weekly_cost_cap", 25.0)

        lines = [f"*Cost today*: ${today_cost:.2f} / ${daily_cap:.2f}"]
        if flags["--week"]:
            week_cost = get_week_cost()
            lines.append(f"*Cost this week*: ${week_cost:.2f} / ${weekly_cap:.2f}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── /model ───────────────────────────────────────────────────

    async def _handle_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        new_model = context.args[0] if context.args else ""
        if new_model:
            valid = {"sonnet", "opus", "haiku", "claude-sonnet-4-20250514",
                     "claude-opus-4-6", "claude-haiku-4-5-20251001"}
            if new_model not in valid:
                return await update.message.reply_text(
                    f"Unknown model: {new_model}\n\n"
                    f"Valid: sonnet, opus, haiku"
                )
            if self._gateway:
                self._gateway.config["model"] = new_model
                # Persist to config.yaml
                import yaml
                config_path = EXODIR / "config.yaml"
                try:
                    cfg = yaml.safe_load(config_path.read_text()) or {}
                    cfg["model"] = new_model
                    config_path.write_text(yaml.dump(cfg, default_flow_style=False))
                except Exception as e:
                    log.warning(f"Failed to persist model change: {e}")
            await update.message.reply_text(f"Model switched to: {new_model}")
        else:
            model = "sonnet"
            if self._gateway:
                model = self._gateway.config.get("model", "sonnet")
            await update.message.reply_text(f"Current model: {model}\n\nUsage: /model <sonnet|opus|haiku>")

    # ── /config — view runtime configuration ─────────────────────

    async def _handle_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current runtime configuration (no secrets)."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        cfg = self._gateway.config if self._gateway else {}

        model = cfg.get("model", "sonnet")
        daily_cap = cfg.get("daily_cost_cap", 5.0)
        weekly_cap = cfg.get("weekly_cost_cap", 25.0)
        session_idle = cfg.get("session_idle_minutes", 120)
        cron_enabled = cfg.get("cron", {}).get("enabled", True)

        platforms = []
        for pname, pcfg in cfg.get("platforms", {}).items():
            status = "enabled" if pcfg.get("enabled", False) else "disabled"
            users = len(pcfg.get("allowed_users", []))
            platforms.append(f"  {pname}: {status} ({users} users)")

        # Autonomy info (ZeroClaw pattern)
        from ..autonomy import format_autonomy_status
        autonomy_info = format_autonomy_status(cfg)

        text = (
            f"Configuration\n\n"
            f"Model: {model}\n"
            f"Daily cap: ${daily_cap:.2f}\n"
            f"Weekly cap: ${weekly_cap:.2f}\n"
            f"Session idle timeout: {session_idle}m\n"
            f"Cron scheduler: {'on' if cron_enabled else 'off'}\n\n"
            f"Platforms:\n" + "\n".join(platforms) + "\n\n"
            f"{autonomy_info}"
        )
        await update.message.reply_text(text)

    # ── /soul — view SOUL.md ─────────────────────────────────────

    async def _handle_soul(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display the agent's SOUL.md personality definition."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        soul_path = EXODIR / "SOUL.md"
        if not soul_path.exists():
            return await update.message.reply_text("SOUL.md not found.")

        soul = soul_path.read_text().strip()
        text = f"SOUL.md ({len(soul)} chars)\n\n{soul}"
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /autonomy — view/change autonomy level ───────────────────

    async def _handle_autonomy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View or change autonomy level. Usage: /autonomy [readonly|supervised|full]"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..autonomy import format_autonomy_status
        from ..config import CONFIG_PATH

        gw = self._gateway
        cfg = gw.config if gw else {}
        raw_args = list(context.args) if context.args else []

        if not raw_args:
            # Just show current autonomy
            text = format_autonomy_status(cfg)
            await update.message.reply_text(text)
            return

        new_level = raw_args[0].lower()
        if new_level not in ("readonly", "supervised", "full"):
            await update.message.reply_text(
                "Usage: /autonomy [readonly|supervised|full]\n\n"
                "- readonly: read-only tools, no writes or bash\n"
                "- supervised: restricted tool set, safe bash only\n"
                "- full: unrestricted (default)"
            )
            return

        # Update config.yaml on disk
        try:
            import yaml
            config_text = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else ""
            config_data = yaml.safe_load(config_text) or {}
            config_data["autonomy"] = new_level
            CONFIG_PATH.write_text(yaml.dump(config_data, default_flow_style=False, sort_keys=False))

            # Hot-reload will pick this up on next message
            from ..config import reload_config
            new_cfg, changes = reload_config()
            if gw:
                gw.config = new_cfg

            await update.message.reply_text(
                f"Autonomy level changed to: *{new_level}*\n\n"
                f"{format_autonomy_status(new_cfg)}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"Failed to update autonomy: {e}")

    # ── /skills — list installed skills ──────────────────────────

    async def _handle_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all installed Claude Code skills."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        skills_dir = Path.home() / ".claude" / "skills"
        if not skills_dir.exists():
            return await update.message.reply_text("No skills directory found.")

        skills = sorted(skills_dir.glob("*/SKILL.md"))
        if not skills:
            return await update.message.reply_text("No skills installed.")

        lines = [f"Installed skills ({len(skills)})\n"]
        for skill_path in skills:
            name = skill_path.parent.name
            # Read first line of description from frontmatter
            desc = ""
            try:
                content = skill_path.read_text()
                for line in content.splitlines():
                    if line.startswith("description:"):
                        desc = line[12:].strip()[:100]
                        break
            except Exception:
                pass

            # Check if disable-model-invocation
            explicit = ""
            try:
                if "disable-model-invocation: true" in skill_path.read_text():
                    explicit = " [explicit]"
            except Exception:
                pass

            lines.append(f"  {name}{explicit}")
            if desc:
                lines.append(f"    {desc}")

        # Queue count
        queue_dir = EXODIR / "skills-queue"
        queued = len(list(queue_dir.glob("*/SKILL.md"))) if queue_dir.exists() else 0
        if queued:
            lines.append(f"\nQueued: {queued} pending approval")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /learnings — list/search past learnings ──────────────────

    async def _handle_learnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List past learnings or search them."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--limit": {"type": "value", "cast": int, "default": 10}})
        limit = min(flags["--limit"], 50)
        query = self._resolve_reply_target(" ".join(raw_args), update)

        from ..session_db import list_learnings, search_learnings

        if query:
            items = search_learnings(query, limit=limit)
        else:
            items = list_learnings(limit=limit)

        if not items:
            msg = "No learnings stored yet. Use `/learn <topic>` to start." if not query else f"No learnings matching `{query}`."
            return await update.message.reply_text(msg, parse_mode="Markdown")

        lines = [f"*Learnings{' matching: ' + query if query else ''}*\n"]
        for item in items:
            verdict = item.get("verdict", "?")
            target = item.get("target", "?")
            patterns = item.get("patterns", "")
            created = item.get("created_at", "")[:10]
            skill = item.get("skill_created", "")

            lines.append(f"*{target}* [{verdict}] ({created})")
            if patterns:
                lines.append(f"  {patterns[:200]}")
            if skill:
                lines.append(f"  Skill: `{skill}`")
            lines.append("")

        text = "\n".join(lines)
        for i in range(0, len(text), 4000):
            await self.app.bot.send_message(
                chat_id=update.message.chat_id, text=text[i:i+4000], parse_mode="Markdown"
            )

    # ── Identity linking ─────────────────────────────────────────

    async def _handle_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Link a cross-platform identity: /link <platform> <user_id> [display_name]"""
        if not self._is_allowed(update):
            return await self._deny(update)

        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /link <platform> <platform_user_id> [display_name]\n\n"
                "Examples:\n"
                "  /link whatsapp 85256171671@s.whatsapp.net Vincent\n"
                "  /link telegram 934847281 Vincent"
            )
            return

        platform = args[0].lower()
        platform_uid = args[1]
        display_name = " ".join(args[2:]) if len(args) > 2 else ""
        # Use the Telegram user ID as canonical
        canonical = str(update.message.from_user.id)

        try:
            from ..session_db import link_identity, get_linked_platforms
            link_identity(canonical, platform, platform_uid, display_name)
            linked = get_linked_platforms(canonical)
            lines = [f"Linked {platform}:{platform_uid} to your identity.\n\nAll linked:"]
            for l in linked:
                name = f" ({l['name']})" if l.get("name") else ""
                lines.append(f"  {l['platform']}: {l['user_id']}{name}")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def _handle_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show linked identities: /whoami"""
        if not self._is_allowed(update):
            return await self._deny(update)

        canonical = str(update.message.from_user.id)
        try:
            from ..session_db import get_linked_platforms
            linked = get_linked_platforms(canonical)
            if not linked:
                await update.message.reply_text(
                    f"No linked identities. Your Telegram ID: {canonical}\n"
                    "Use /link to connect other platforms.")
                return
            lines = [f"Canonical ID: {canonical}\n\nLinked platforms:"]
            for l in linked:
                name = f" ({l['name']})" if l.get("name") else ""
                lines.append(f"  {l['platform']}: {l['user_id']}{name}")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    # ── Background tasks (Phase 3) ────────────────────────────────

    async def _handle_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List background tasks: /tasks"""
        if not self._is_allowed(update):
            return await self._deny(update)

        try:
            mgr = self._gateway._background_mgr
            tasks = mgr.list_tasks(include_completed=True)
            if not tasks:
                await update.message.reply_text("No background tasks.")
                return
            lines = ["Background tasks:\n"]
            for t in tasks[:15]:
                lines.append(t.to_summary())
            active = mgr.active_count()
            lines.append(f"\nActive: {active}/{mgr._executor._max_workers}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def _handle_cancel_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel a background task: /cancel <task_id>"""
        if not self._is_allowed(update):
            return await self._deny(update)

        if not context.args:
            await update.message.reply_text("Usage: /cancel <task_id>")
            return

        task_id = context.args[0]
        try:
            mgr = self._gateway._background_mgr
            # Try prefix match
            matching = [t for t in mgr.list_tasks()
                        if t.id.startswith(task_id)]
            if not matching:
                await update.message.reply_text(f"No task found matching '{task_id}'")
                return
            cancelled = await mgr.cancel(matching[0].id)
            if cancelled:
                await update.message.reply_text(
                    f"Cancelled task {matching[0].id[:8]}: {matching[0].description}")
            else:
                await update.message.reply_text(
                    f"Task {matching[0].id[:8]} is not cancellable (status: {matching[0].status})")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def _handle_hooks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show registered hooks: /hooks"""
        if not self._is_allowed(update):
            return await self._deny(update)

        try:
            from ..hooks import hooks
            registered = hooks.registered_hooks()
            if not registered:
                await update.message.reply_text("No hook listeners registered.")
                return
            lines = ["Registered hooks:\n"]
            for name, count in sorted(registered.items()):
                lines.append(f"  {name}: {count} listener(s)")
            lines.append(f"\nTotal: {sum(registered.values())} listeners "
                        f"across {len(registered)} hook points")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    # ── Config hot-reload (Phase 4) ──────────────────────────────

    async def _handle_reload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Force-reload config: /reload"""
        if not self._is_allowed(update):
            return await self._deny(update)

        try:
            from ..config import reload_config, validate_config
            new_config, changes = reload_config()

            # Validate before applying
            errors = validate_config(new_config)
            if errors:
                await update.message.reply_text(
                    "Config validation errors:\n" +
                    "\n".join(f"  - {e}" for e in errors) +
                    "\n\nConfig NOT applied.")
                return

            self._gateway.config = new_config
            if changes:
                await update.message.reply_text(
                    f"Config reloaded. Changed:\n" +
                    "\n".join(f"  - {c}" for c in changes))
            else:
                await update.message.reply_text("Config reloaded. No changes detected.")

            # Fire hook
            try:
                from ..hooks import hooks
                await hooks.fire_void("config_reload", changes=changes)
            except Exception:
                pass
        except Exception as e:
            await update.message.reply_text(f"Reload failed: {e}")

    # ── Exec allowlist management (Phase 4) ──────────────────────

    async def _handle_allowlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage exec allowlist: /allowlist [add|rm|clear] [pattern|id]"""
        if not self._is_allowed(update):
            return await self._deny(update)

        args = context.args or []

        try:
            from ..exec_allowlist import ExecAllowlist
            al = ExecAllowlist(self._gateway.config)

            if not args:
                # Show current allowlist
                entries = al.list_entries()
                if not entries:
                    await update.message.reply_text(
                        "Exec allowlist is empty.\n"
                        "Use /allowlist add <pattern> to add entries.")
                    return
                lines = ["Exec allowlist:\n"]
                for e in entries:
                    used = f" (used {e.use_count}x)" if e.use_count else ""
                    lines.append(f"  [{e.id}] {e.pattern}{used}")
                lines.append(f"\nSecurity: {al.security} | Ask: {al.ask}")
                await update.message.reply_text("\n".join(lines))
                return

            subcmd = args[0].lower()

            if subcmd == "add" and len(args) >= 2:
                pattern = args[1]
                user_id = str(update.message.from_user.id)
                entry = al.add_entry(pattern, added_by=user_id)
                await update.message.reply_text(
                    f"Added to allowlist: [{entry.id}] {entry.pattern}")

            elif subcmd == "rm" and len(args) >= 2:
                entry_id = args[1]
                if al.remove_entry(entry_id):
                    await update.message.reply_text(f"Removed allowlist entry: {entry_id}")
                else:
                    await update.message.reply_text(f"Entry not found: {entry_id}")

            elif subcmd == "clear":
                count = len(al.list_entries())
                for e in al.list_entries():
                    al.remove_entry(e.id)
                await update.message.reply_text(f"Cleared {count} allowlist entries.")

            else:
                await update.message.reply_text(
                    "Usage:\n"
                    "  /allowlist — show current allowlist\n"
                    "  /allowlist add <pattern> — add entry\n"
                    "  /allowlist rm <id> — remove entry\n"
                    "  /allowlist clear — remove all entries")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    # ── /doctor — system health check ────────────────────────────

    async def _handle_doctor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run self-audit health check: /doctor"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        try:
            from ..self_audit import run_audit
            cfg = self._gateway.config if self._gateway else {}
            report = run_audit(cfg)
            text = report.format_text()
            if len(text) > 4000:
                text = text[:3950] + "\n\n... [truncated]"
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"Doctor failed: {e}")
