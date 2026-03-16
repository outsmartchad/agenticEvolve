"""Approval command handlers mixin — extracted from TelegramAdapter."""
from __future__ import annotations
import logging
from pathlib import Path

log = logging.getLogger(__name__)

EXODIR = Path.home() / ".agenticEvolve"

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class ApprovalMixin:

    # ── /queue — list skills pending approval ────────────────────

    async def _handle_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        from ..evolve import list_queue
        items = list_queue()

        if not items:
            return await update.message.reply_text("Skills queue is empty. Run /evolve to discover new tools.")

        lines = ["*Skills queue*\n"]
        for item in items:
            status = item["status"]
            name = item["name"]
            if status == "rejected":
                issues = item.get("review", {}).get("issues", [])
                lines.append(f"  `{name}` — rejected ({', '.join(issues[:2])})")
                lines.append(f"    /approve {name} force")
            else:
                lines.append(f"  `{name}` — pending review")
                lines.append(f"    /approve {name}")
            lines.append(f"    /reject {name}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── /approve — install a queued skill ────────────────────────

    async def _handle_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--force": {"aliases": ["force"], "type": "bool"}})
        if not raw_args:
            return await update.message.reply_text("Usage: `/approve <skill-name> [--force]`", parse_mode="Markdown")

        name = raw_args[0]
        force = flags["--force"]

        from ..evolve import approve_skill, approve_skill_force
        if force:
            ok, msg = approve_skill_force(name)
        else:
            ok, msg = approve_skill(name)

        await update.message.reply_text(msg, parse_mode="Markdown")

    # ── /reject — remove a queued skill ──────────────────────────

    async def _handle_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        args = context.args if context.args else []
        if not args:
            return await update.message.reply_text("Usage: `/reject <skill-name> [reason]`", parse_mode="Markdown")

        name = args[0]
        reason = " ".join(args[1:]) if len(args) > 1 else ""

        from ..evolve import reject_skill
        ok, msg = reject_skill(name, reason)
        await update.message.reply_text(msg, parse_mode="Markdown")

    # ── /scan-skills — AgentShield retrospective scan ─────────────

    async def _handle_scan_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run AgentShield on all installed skills and report findings."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        import subprocess as sp
        await update.message.reply_text("*AgentShield: scanning all installed skills...*", parse_mode="Markdown")

        try:
            result = sp.run(
                ["npx", "ecc-agentshield", "scan", "--path", str(Path.home() / ".claude"), "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout.strip()

            import json
            try:
                data = json.loads(output)
                grade = data.get("grade", "?")
                score = data.get("score", "?")
                findings = data.get("findings", [])
                critical = [f for f in findings if f.get("severity") == "critical"]
                high = [f for f in findings if f.get("severity") == "high"]

                lines = [f"*AgentShield scan complete*\nGrade: {grade} ({score}/100)\n"]
                if critical:
                    lines.append(f"🔴 Critical ({len(critical)}):")
                    for f in critical[:5]:
                        lines.append(f"  - {f.get('message', '?')}")
                if high:
                    lines.append(f"🟡 High ({len(high)}):")
                    for f in high[:5]:
                        lines.append(f"  - {f.get('message', '?')}")
                if not critical and not high:
                    lines.append("✅ No critical or high findings.")

                # Audit log
                try:
                    from ..session_db import log_audit, generate_trace_id
                    log_audit(
                        trace_id=generate_trace_id(),
                        stage="SCAN",
                        action="agentshield_retro",
                        result="ok",
                        metadata={"grade": grade, "score": score, "critical": len(critical), "high": len(high)},
                    )
                except Exception:
                    pass

                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

            except (json.JSONDecodeError, ValueError):
                lines = output.splitlines()
                await update.message.reply_text(
                    "*AgentShield output:*\n" + "\n".join(lines[:15]),
                    parse_mode="Markdown",
                )

        except sp.TimeoutExpired:
            await update.message.reply_text("AgentShield scan timed out (120s).")
        except FileNotFoundError:
            await update.message.reply_text("npx not found — install Node.js to run AgentShield.")
        except Exception as e:
            await update.message.reply_text(f"AgentShield error: {e}")
