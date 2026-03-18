"""Context window management (OpenClaw pattern).

Monitors and manages the context window to prevent overflow:
  - Token estimation (char-based, ~4 chars per token)
  - Pre-flight context size guard
  - Auto-compaction when context exceeds threshold
  - Session summarization for very long conversations

Claude's context window:
  - Sonnet 4.6: 200K tokens (~800K chars)
  - Opus 4.6: 200K tokens (~800K chars)
  - We aim to stay under 50K tokens (~200K chars) for prompt+history+context
  - Reserve at least 16K tokens (~64K chars) for response generation
"""
import logging
import subprocess
from typing import Optional

log = logging.getLogger("agenticEvolve.context")

# ── Token estimation ─────────────────────────────────────────────

# Conservative estimate: ~3.5 chars per token for English text
CHARS_PER_TOKEN = 3.5

# Model context limits (in tokens)
MODEL_CONTEXT_LIMITS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
}

# We target staying under this fraction of the context window
TARGET_USAGE = 0.25  # 25% — leaves room for Claude's own tool calls + response
# Minimum free tokens for response generation
MIN_FREE_TOKENS = 16_000


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count."""
    return int(len(text) / CHARS_PER_TOKEN)


def estimate_chars(tokens: int) -> int:
    """Estimate character count from token count."""
    return int(tokens * CHARS_PER_TOKEN)


# ── Context size guard ───────────────────────────────────────────

def check_context_size(prompt: str, model: str = "sonnet",
                       config: dict | None = None) -> dict:
    """Check if the prompt fits within the context window.

    Returns:
        {
            "ok": bool,
            "estimated_tokens": int,
            "limit_tokens": int,
            "usage_pct": float,
            "action": str  # "ok", "warn", "compact", "reject"
        }
    """
    est_tokens = estimate_tokens(prompt)
    limit = MODEL_CONTEXT_LIMITS.get(model, 200_000)

    # Configurable thresholds
    ctx_cfg = (config or {}).get("context", {})
    warn_pct = ctx_cfg.get("warn_pct", 0.4)
    compact_pct = ctx_cfg.get("compact_pct", 0.6)
    reject_pct = ctx_cfg.get("reject_pct", 0.85)

    usage_pct = est_tokens / limit

    if usage_pct >= reject_pct:
        action = "reject"
    elif usage_pct >= compact_pct:
        action = "compact"
    elif usage_pct >= warn_pct:
        action = "warn"
    else:
        action = "ok"

    return {
        "ok": action in ("ok", "warn"),
        "estimated_tokens": est_tokens,
        "limit_tokens": limit,
        "usage_pct": round(usage_pct, 3),
        "action": action,
    }


# ── LLM summarization helper ─────────────────────────────────────

def _llm_summarize_messages(messages: list[dict], target_chars: int = 500) -> str | None:
    """Summarize conversation messages using Claude Sonnet.
    Returns summary string or None on failure.
    """
    # Format messages for the prompt
    formatted = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")[:300]  # cap each msg
        formatted.append(f"[{role}]: {content}")

    text = "\n".join(formatted)
    if len(text) > 8000:
        text = text[:8000] + "\n... [truncated]"

    prompt = (
        f"Summarize this conversation segment in 3-5 concise bullet points "
        f"(under {target_chars} chars total). Focus on key decisions, "
        f"facts, and action items. No preamble.\n\n{text}"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "claude-sonnet-4-20250514"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            summary = result.stdout.strip()
            if len(summary) <= target_chars * 2:  # sanity check
                return summary
    except Exception as e:
        log.debug(f"LLM summarization failed: {e}")

    return None


# ── Auto-compaction ──────────────────────────────────────────────

def compact_history(history: list[dict], target_chars: int = 6000) -> list[dict]:
    """Aggressively compact history to fit within target_chars.

    Strategy:
    1. Keep the first message (establishes context)
    2. Keep the last 5 messages (recent context)
    3. Summarize the middle as a single "[conversation summary]" message
    4. Truncate individual messages if still too large
    """
    if not history:
        return []

    total_chars = sum(len(m.get("content", "")) for m in history)
    if total_chars <= target_chars:
        return history

    if len(history) <= 6:
        # Too few messages to summarize — just truncate each
        compacted = []
        per_msg = max(200, target_chars // len(history))
        for m in history:
            content = m.get("content", "")
            if len(content) > per_msg:
                content = content[:per_msg] + "... [truncated]"
            compacted.append({**m, "content": content})
        return compacted

    # Keep first + last 5, summarize middle
    first = history[0]
    last_5 = history[-5:]
    middle = history[1:-5]

    # Try LLM summarization first (better quality, ~$0.01)
    llm_summary = _llm_summarize_messages(middle)
    if llm_summary:
        summary_msg = {
            "role": "system",
            "content": f"[AI summary of {len(middle)} earlier messages]\n{llm_summary}"
        }
    else:
        # Fallback: truncation-based summary
        summary_parts = []
        for m in middle:
            role = m.get("role", "user")
            content = m.get("content", "")[:100]
            summary_parts.append(f"- [{role}] {content}")
        middle_summary = "\n".join(summary_parts)
        if len(middle_summary) > 1500:
            middle_summary = middle_summary[:1500] + f"\n... [{len(middle)} messages compacted]"
        summary_msg = {
            "role": "system",
            "content": f"[Conversation summary — {len(middle)} earlier messages compacted]\n{middle_summary}"
        }

    result = [first, summary_msg] + last_5

    # Final check — truncate if still over
    total = sum(len(m.get("content", "")) for m in result)
    if total > target_chars:
        per_msg = max(200, target_chars // len(result))
        result = [
            {**m, "content": m.get("content", "")[:per_msg] + "... [truncated]"}
            if len(m.get("content", "")) > per_msg else m
            for m in result
        ]

    log.info(f"Context compaction: {len(history)} msgs ({total_chars} chars) → "
             f"{len(result)} msgs ({sum(len(m.get('content', '')) for m in result)} chars)")
    return result


def auto_compact_if_needed(history: list[dict], session_context: str,
                           message: str, model: str = "sonnet",
                           config: dict | None = None) -> list[dict]:
    """Auto-compact history if the total context would be too large.

    Returns the (possibly compacted) history.
    """
    # Estimate total context size
    from .agent import _format_history
    formatted = _format_history(history)
    total = len(session_context) + len(formatted) + len(message) + 500  # overhead

    check = check_context_size("x" * total, model, config)

    if check["action"] == "compact":
        log.warning(f"Context at {check['usage_pct']*100:.0f}% — auto-compacting history")
        return compact_history(history, target_chars=4000)
    elif check["action"] == "reject":
        log.warning(f"Context at {check['usage_pct']*100:.0f}% — aggressive compaction")
        return compact_history(history, target_chars=2000)

    return history
