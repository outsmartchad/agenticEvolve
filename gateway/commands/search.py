"""Search command handlers mixin — extracted from TelegramAdapter."""
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


class SearchMixin:

    # ── /search — FTS5 search across past sessions ─────────────

    async def _handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search past sessions using FTS5. Usage: /search <query> [--limit N]"""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        flags = self._parse_flags(raw_args, {"--limit": {"type": "value", "cast": int, "default": 5}})
        limit = min(flags["--limit"], 20)
        query = self._resolve_reply_target(" ".join(raw_args), update)
        if not query:
            await update.message.reply_text(
                "Usage: /search <query> [--limit N]\n\n"
                "Examples:\n"
                "/search telegram rate limit\n"
                "/search --limit 10 cost cap\n"
                "/search absorb pipeline\n\n"
                "Tip: Reply to a message and send /search to search for its content"
            )
            return

        from ..session_db import search_sessions
        results = search_sessions(query, limit=limit)

        if not results:
            await update.message.reply_text(f"No results for: {query}")
            return

        lines = [f"Search results for: {query}\n"]
        for r in results:
            title = r.get("title", "Untitled") or "Untitled"
            sid = r["session_id"][:8]
            started = r.get("started_at", "")[:10]
            match_count = len(r.get("matches", []))
            lines.append(f"\n[{sid}] {title} ({started})")
            for m in r.get("matches", [])[:2]:
                snippet = m["content"][:200].replace("\n", " ")
                lines.append(f"  {m['role']}: {snippet}")
            if match_count > 2:
                lines.append(f"  ... +{match_count - 2} more matches")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... [truncated]"
        await update.message.reply_text(text)

    # ── /recall — cross-layer unified search ────────────────────

    async def _handle_recall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search across ALL memory layers: sessions, learnings, instincts, memory, user profile."""
        if not update.message:
            return
        if not self._is_allowed(update.message.from_user.id):
            return await self._deny(update)

        raw_args = list(context.args) if context.args else []
        query = self._resolve_reply_target(" ".join(raw_args), update)
        if not query:
            await update.message.reply_text(
                "Usage: /recall <query>\n\n"
                "Searches ALL memory layers at once:\n"
                "- Past conversations (sessions)\n"
                "- Absorbed knowledge (learnings)\n"
                "- Observed patterns (instincts)\n"
                "- Agent notes (MEMORY.md)\n"
                "- User profile (USER.md)\n\n"
                "Tip: Reply to a message with /recall to search for its content"
            )
            return

        from ..session_db import unified_search, format_recall_context

        # Get active session ID if available
        chat_id = str(update.message.chat_id)
        key = f"telegram:{chat_id}"
        session_id = ""
        if self._gateway:
            session_id = self._gateway._active_sessions.get(key, "")

        results = unified_search(query, session_id=session_id, limit_per_layer=5)

        if not results:
            await update.message.reply_text(f"No results across any memory layer for: {query}")
            return

        # Format with source grouping
        formatted = format_recall_context(results, max_chars=3800)
        header = f"Recall: {query}\n{len(results)} results across {len(set(r.get('source','') for r in results))} layers\n"
        text = header + "\n" + formatted

        try:
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(text)
