"""Watchdog — proactive signal monitor.

Polls signal files every 30 minutes during waking hours (07:00–23:00 HKT).
If a new signal scores ≥ 8.5 it hasn't notified about yet, push it to Telegram
without waiting for the user to ask.

Signal scoring is lightweight (no Claude invocation) — purely heuristic based
on source metadata and keyword presence.

Integration: GatewayRunner spawns _watchdog_loop as a background asyncio task.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("agenticEvolve.watchdog")

EXODIR = Path.home() / ".agenticEvolve"
SIGNALS_DIR = EXODIR / "signals"
SEEN_FILE = EXODIR / "watchdog_seen.json"

# HKT = UTC+8
HKT = timezone(timedelta(hours=8))
WAKING_START = 7   # 07:00 HKT
WAKING_END = 23    # 23:00 HKT

SCORE_THRESHOLD = 8.5
POLL_INTERVAL = 30 * 60  # 30 minutes

# Keywords that boost score (+1 each, max +3)
HIGH_SIGNAL_KEYWORDS = [
    "claude code", "mcp server", "agent loop", "agentic", "autonomous agent",
    "multi-agent", "tool use", "function calling", "o3", "claude 4",
    "gemini 2", "gpt-5", "anthropic", "openai", "deepmind",
]


def _load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_seen(seen: set[str]):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def _score_signal(obj: dict) -> float:
    """Heuristic score 0–10 for a signal object."""
    score = 5.0  # baseline

    # Source boosts
    source = obj.get("source", "")
    if source == "github":
        score += 1.0
    elif source == "hn":
        score += 0.5

    # Metadata boosts
    meta = obj.get("metadata", {})
    points = meta.get("points", 0) or meta.get("stars", 0) or 0
    if points > 500:
        score += 2.0
    elif points > 100:
        score += 1.0
    elif points > 30:
        score += 0.5

    # Keyword boosts (cap at +3)
    text = (
        (obj.get("title") or "") + " " +
        (obj.get("content") or "") + " " +
        (obj.get("description") or "")
    ).lower()
    keyword_hits = sum(1 for kw in HIGH_SIGNAL_KEYWORDS if kw in text)
    score += min(keyword_hits, 3)

    return min(score, 10.0)


def _format_signal(obj: dict, score: float) -> str:
    """Format a signal for Telegram notification."""
    title = obj.get("title", obj.get("name", "(untitled)"))[:80]
    source = obj.get("source", "?").upper()
    url = obj.get("url", "")
    meta = obj.get("metadata", {})
    points = meta.get("points", meta.get("stars", 0)) or 0

    lines = [
        f"*[Watchdog] High-signal detect ({score:.1f}/10)*",
        f"[{source}] {title}",
    ]
    if points:
        lines.append(f"Points/stars: {points}")
    if url:
        lines.append(url)
    return "\n".join(lines)


def _is_waking_hours() -> bool:
    now_hkt = datetime.now(HKT)
    return WAKING_START <= now_hkt.hour < WAKING_END


async def _watchdog_loop(gateway, chat_id: str, shutdown_event: asyncio.Event):
    """Main watchdog loop. Runs until shutdown_event is set."""
    log.info("Watchdog started")
    seen = _load_seen()

    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(POLL_INTERVAL)
            if shutdown_event.is_set():
                break

            if not _is_waking_hours():
                log.debug("Watchdog: outside waking hours, skipping scan")
                continue

            # Scan today's and yesterday's signal dirs
            found: list[tuple[float, dict]] = []
            now = datetime.now(timezone.utc)
            for delta_days in (0, 1):
                day_str = (now - timedelta(days=delta_days)).strftime("%Y-%m-%d")
                sig_dir = SIGNALS_DIR / day_str
                if not sig_dir.exists():
                    continue
                for f in sig_dir.glob("*.json"):
                    try:
                        content = f.read_text().strip()
                        for line in content.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            obj = json.loads(line)
                            sig_id = obj.get("id") or f"{f.stem}:{obj.get('title','')[:30]}"
                            if sig_id in seen:
                                continue
                            score = _score_signal(obj)
                            if score >= SCORE_THRESHOLD:
                                found.append((score, obj, sig_id))
                    except Exception as e:
                        log.debug(f"Watchdog parse error {f}: {e}")

            if not found:
                log.debug("Watchdog: no new high-signal items")
                continue

            # Sort by score desc, notify top 3
            found.sort(key=lambda x: x[0], reverse=True)
            adapter = gateway._adapter_map.get("telegram")
            if not adapter:
                log.warning("Watchdog: no telegram adapter, skipping notify")
                continue

            for score, obj, sig_id in found[:3]:
                msg = _format_signal(obj, score)
                try:
                    await adapter.app.bot.send_message(
                        chat_id=int(chat_id), text=msg, parse_mode="Markdown"
                    )
                    log.info(f"Watchdog: notified [{sig_id}] score={score:.1f}")
                except Exception as e:
                    log.warning(f"Watchdog: send failed: {e}")
                seen.add(sig_id)

            _save_seen(seen)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Watchdog error: {e}")

    log.info("Watchdog stopped")
