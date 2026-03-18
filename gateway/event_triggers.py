"""Default event triggers for the gateway."""

import logging
from .event_bus import event_bus

log = logging.getLogger("agenticEvolve.event_triggers")


async def _on_cost_threshold(event_type: str, data: dict):
    """Alert user when cost approaches daily cap."""
    pct = data.get("pct", 0)
    today = data.get("today_cost", 0)
    cap = data.get("daily_cap", 0)
    if pct >= 0.8:
        # Send Telegram alert
        try:
            from .platforms.telegram import send_alert
            await send_alert(
                f"Cost alert: ${today:.2f} / ${cap:.2f} "
                f"({pct * 100:.0f}% of daily cap)"
            )
        except Exception:
            log.warning(
                f"Cost threshold {pct * 100:.0f}% but couldn't send alert"
            )


async def _on_error_streak(event_type: str, data: dict):
    """Run self-diagnostic after consecutive errors."""
    count = data.get("count", 0)
    if count >= 3:
        log.warning(
            f"Error streak: {count} consecutive errors, running self-audit"
        )
        try:
            from .self_audit import run_audit
            results = run_audit()
            log.info(f"Self-audit results: {results}")
        except Exception as e:
            log.error(f"Self-audit failed: {e}")


async def _on_adapter_reconnect(event_type: str, data: dict):
    """Log adapter reconnection."""
    platform = data.get("platform", "unknown")
    log.info(f"Adapter reconnected: {platform}")


def register_default_triggers():
    """Register all default event triggers. Called on gateway start."""
    event_bus.on("cost:threshold", _on_cost_threshold)
    event_bus.on("error:streak", _on_error_streak)
    event_bus.on("adapter:reconnect", _on_adapter_reconnect)
    log.info("Default event triggers registered")
