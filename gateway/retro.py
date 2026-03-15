"""Retro module — mandatory reflection stage before evolving forward.

Fires after any digest (WeChat, morning, evolve) and produces a gap report:
  - What failed in the last cycle?
  - What patterns were we supposed to adopt but didn't?
  - What does the community know that we don't?

Context types:
  - "wechat"  — WeChat group digest summary
  - "digest"  — morning briefing digest
  - "evolve"  — end-of-evolve-cycle summary

Output: gap report text (sent to Telegram by the caller).
Cost tracked and returned.
"""
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger("agenticEvolve.retro")

EXODIR = Path.home() / ".agenticEvolve"
RETRO_LOG = EXODIR / "logs" / "retro.log"


def _load_memory_snapshot() -> str:
    """Load bounded memory for retro context."""
    memory_dir = Path.home() / ".claude" / "projects" / "-Users-chiwangso" / "memory"
    snippets = []
    for fname in ("MEMORY.md", "project_agenticevolve.md", "feedback_general.md"):
        fpath = memory_dir / fname
        if fpath.exists():
            text = fpath.read_text()[:2000]
            snippets.append(f"### {fname}\n{text}")
    return "\n\n".join(snippets)


def _load_evolve_log() -> str:
    """Load the last N lines of the evolve/cycle log for context."""
    log_path = EXODIR / "logs" / "gateway.log"
    if not log_path.exists():
        return ""
    lines = log_path.read_text().splitlines()
    # Last 50 lines covering recent cycle activity
    return "\n".join(lines[-50:])


def run_retro(
    context_type: str,
    context_data: str,
    on_progress: Callable[[str], None] | None = None,
    model: str = "claude-haiku-4-5-20251001",
) -> tuple[str, float]:
    """Run the retro reflection agent.

    Args:
        context_type: "wechat" | "digest" | "evolve"
        context_data: The digest/summary text that triggered the retro
        on_progress: Optional callback for streaming progress updates
        model: Model to use (defaults to Haiku for cost efficiency)

    Returns:
        (gap_report_text, cost_usd)
    """
    from .agent import invoke_claude_streaming

    _progress = on_progress or (lambda x: None)
    _progress("*Retro: reflecting on gaps...*")

    memory_snapshot = _load_memory_snapshot()
    recent_log = _load_evolve_log()

    context_label = {
        "wechat": "WeChat group digest",
        "digest": "morning briefing digest",
        "evolve": "evolve cycle summary",
    }.get(context_type, context_type)

    prompt = (
        f"You are the RETRO agent in agenticEvolve — a mandatory reflection stage.\n\n"
        f"A {context_label} just completed. Before we evolve forward, reflect on gaps.\n\n"
        f"## Current Memory State\n{memory_snapshot}\n\n"
        f"## Recent System Log (last 50 lines)\n```\n{recent_log}\n```\n\n"
        f"## {context_label.title()}\n{context_data}\n\n"
        f"## Your Task\n"
        f"Identify 3–5 concrete gaps. For each gap, answer:\n"
        f"1. What is missing or broken?\n"
        f"2. What is the evidence from the digest or log?\n"
        f"3. What should be done (one action, specific)?\n\n"
        f"Format as a compact retro report. Use this structure:\n\n"
        f"**Gap 1 — [short label]**\n"
        f"Evidence: ...\n"
        f"Action: ...\n\n"
        f"Keep it under 400 words. No filler. Focus on ACTIONABLE gaps only.\n"
        f"If there are no meaningful gaps, say so in one sentence.\n\n"
        f"Do NOT create any files. ONLY reflect and return the gap report."
    )

    result = invoke_claude_streaming(
        prompt,
        on_progress=_progress,
        model=model,
        session_context=f"[Retro/{context_type}]",
        allowed_tools=["Read", "Glob", "Grep"],
    )

    text = result.get("text", "Retro: no gaps identified.")
    cost = result.get("cost", 0.0)

    # Append to retro log
    try:
        RETRO_LOG.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        with open(RETRO_LOG, "a") as f:
            f.write(f"\n---\n[{ts}] context_type={context_type}\n{text}\n")
    except Exception as e:
        log.warning(f"Failed to write retro log: {e}")

    log.info(f"Retro complete (type={context_type}, cost=${cost:.4f})")
    return text, cost
