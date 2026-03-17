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
import re
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("agenticEvolve.retro")

EXODIR = Path.home() / ".agenticEvolve"
RETRO_LOG = EXODIR / "logs" / "retro.log"
INSTINCTS_DIR = Path.home() / ".agenticEvolve" / "instincts"


def _write_instincts(gap_report: str, context_type: str) -> int:
    """Parse gap report and write each gap as a YAML instinct file.

    Returns number of instincts written.
    """
    # Match "**Gap N — Label**" or "Gap N — Label" patterns
    gap_pattern = re.compile(
        r"\*{0,2}Gap\s+\d+\s*[—–-]+\s*(.+?)\*{0,2}\n(.*?)(?=\*{0,2}Gap\s+\d+|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    matches = gap_pattern.findall(gap_report)
    if not matches:
        return 0

    INSTINCTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    written = 0

    for label_raw, body in matches:
        label = label_raw.strip().rstrip("*").strip()
        slug = re.sub(r"[^\w]+", "-", label.lower()).strip("-")[:60]
        fname = f"{ts.strftime('%Y%m%d')}_{slug}.yaml"
        fpath = INSTINCTS_DIR / fname

        # Don't overwrite — same gap may surface across cycles; bump confidence instead
        if fpath.exists():
            try:
                existing = yaml.safe_load(fpath.read_text()) or {}
                current_conf = existing.get("confidence", 0.3)
                existing["confidence"] = min(round(current_conf + 0.1, 1), 0.9)
                existing["last_seen"] = ts.isoformat()
                existing["seen_count"] = existing.get("seen_count", 1) + 1
                fpath.write_text(yaml.dump(existing, allow_unicode=True))
                log.info(f"Instinct bumped: {fname} → conf={existing['confidence']}")
            except Exception as e:
                log.warning(f"Failed to update instinct {fname}: {e}")
            continue

        instinct = {
            "label": label,
            "source": f"retro/{context_type}",
            "confidence": 0.3,
            "status": "open",
            "created_at": ts.isoformat(),
            "last_seen": ts.isoformat(),
            "seen_count": 1,
            "body": body.strip(),
        }
        try:
            fpath.write_text(yaml.dump(instinct, allow_unicode=True))
            log.info(f"Instinct written: {fname}")
            written += 1
        except Exception as e:
            log.warning(f"Failed to write instinct {fname}: {e}")

    return written


def _load_memory_snapshot() -> str:
    """Load bounded memory for retro context."""
    memory_dir = Path.home() / ".agenticEvolve" / "memory"
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
    model: str = "claude-sonnet-4-6",
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
        ts = datetime.now(timezone.utc).isoformat()
        with open(RETRO_LOG, "a") as f:
            f.write(f"\n---\n[{ts}] context_type={context_type}\n{text}\n")
    except Exception as e:
        log.warning(f"Failed to write retro log: {e}")

    # Persist gaps as instinct YAML files
    n_instincts = _write_instincts(text, context_type)
    if n_instincts:
        log.info(f"Instincts written: {n_instincts} new gap(s) → {INSTINCTS_DIR}")

    log.info(f"Retro complete (type={context_type}, cost=${cost:.4f})")
    return text, cost
