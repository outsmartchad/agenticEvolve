"""Diagnostic event bus — structured observability for the gateway.

Adapted from OpenClaw's diagnostic-events.ts. Emits typed events for:
- Message processing (queued, processed, duration, outcome)
- Model usage (tokens, cost, model, latency)
- Session state changes
- Tool loop detections
- System health heartbeats
"""
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("agenticEvolve.diagnostics")

EXODIR = Path.home() / ".agenticEvolve"
DIAGNOSTICS_LOG = EXODIR / "logs" / "diagnostics.jsonl"


# ── Event Types ──────────────────────────────────────────────

@dataclass
class DiagnosticEvent:
    """Base diagnostic event."""
    type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    seq: int = 0


@dataclass
class MessageEvent(DiagnosticEvent):
    """Message processing event."""
    type: str = "message"
    platform: str = ""
    chat_id: str = ""
    user_id: str = ""
    phase: str = ""  # "queued", "processing", "completed", "failed"
    duration_ms: float = 0
    prompt_chars: int = 0
    response_chars: int = 0
    model: str = ""
    cost: float = 0


@dataclass
class UsageEvent(DiagnosticEvent):
    """Model usage event."""
    type: str = "usage"
    model: str = ""
    prompt_chars: int = 0
    response_chars: int = 0
    cost: float = 0
    latency_ms: float = 0
    session_id: str = ""


@dataclass
class SessionEvent(DiagnosticEvent):
    """Session state change."""
    type: str = "session"
    session_id: str = ""
    platform: str = ""
    chat_id: str = ""
    state: str = ""  # "created", "active", "idle", "expired"


@dataclass
class LoopEvent(DiagnosticEvent):
    """Tool loop detection event."""
    type: str = "tool_loop"
    session_id: str = ""
    mode: str = ""
    level: str = ""
    count: int = 0
    tool_name: str = ""
    message: str = ""


@dataclass
class HeartbeatEvent(DiagnosticEvent):
    """Periodic system health heartbeat."""
    type: str = "heartbeat"
    uptime_secs: float = 0
    active_sessions: int = 0
    messages_today: int = 0
    cost_today: float = 0
    platforms: dict = field(default_factory=dict)


# ── Event Bus ────────────────────────────────────────────────

EventListener = Callable[[DiagnosticEvent], None]

_listeners: list[EventListener] = []
_seq: int = 0
_recent: deque[DiagnosticEvent] = deque(maxlen=200)
_recursion_depth: int = 0
_MAX_RECURSION: int = 5


def on_event(listener: EventListener) -> Callable:
    """Register an event listener. Returns unsubscribe function."""
    _listeners.append(listener)
    def unsubscribe():
        if listener in _listeners:
            _listeners.remove(listener)
    return unsubscribe


def emit(event: DiagnosticEvent) -> None:
    """Emit a diagnostic event to all listeners."""
    global _seq, _recursion_depth

    if _recursion_depth >= _MAX_RECURSION:
        return

    _seq += 1
    event.seq = _seq
    _recent.append(event)

    _recursion_depth += 1
    try:
        for listener in _listeners:
            try:
                listener(event)
            except Exception as e:
                log.debug(f"Diagnostic listener error: {e}")
    finally:
        _recursion_depth -= 1


def get_recent(n: int = 50, event_type: str | None = None) -> list[DiagnosticEvent]:
    """Get recent events, optionally filtered by type."""
    events = list(_recent)
    if event_type:
        events = [e for e in events if e.type == event_type]
    return events[-n:]


# ── JSONL file sink ──────────────────────────────────────────

_jsonl_file = None


def _jsonl_sink(event: DiagnosticEvent) -> None:
    """Write events to a JSONL file."""
    global _jsonl_file
    try:
        if _jsonl_file is None:
            DIAGNOSTICS_LOG.parent.mkdir(parents=True, exist_ok=True)
            _jsonl_file = open(DIAGNOSTICS_LOG, "a")
        _jsonl_file.write(json.dumps(asdict(event), default=str) + "\n")
        _jsonl_file.flush()
    except Exception:
        pass


def enable_jsonl_logging() -> Callable:
    """Enable JSONL file logging. Returns unsubscribe function."""
    return on_event(_jsonl_sink)


# ── Convenience emitters ─────────────────────────────────────

def emit_message(platform: str, chat_id: str, user_id: str, phase: str,
                  duration_ms: float = 0, prompt_chars: int = 0,
                  response_chars: int = 0, model: str = "", cost: float = 0):
    emit(MessageEvent(
        platform=platform, chat_id=chat_id, user_id=user_id,
        phase=phase, duration_ms=duration_ms, prompt_chars=prompt_chars,
        response_chars=response_chars, model=model, cost=cost,
    ))


def emit_usage(model: str, prompt_chars: int, response_chars: int,
                cost: float, latency_ms: float, session_id: str = ""):
    emit(UsageEvent(
        model=model, prompt_chars=prompt_chars, response_chars=response_chars,
        cost=cost, latency_ms=latency_ms, session_id=session_id,
    ))


def emit_loop(session_id: str, mode: str, level: str, count: int,
               tool_name: str, message: str):
    emit(LoopEvent(
        session_id=session_id, mode=mode, level=level,
        count=count, tool_name=tool_name, message=message,
    ))


# ── Status summary ───────────────────────────────────────────

def get_status_summary() -> dict:
    """Get a summary of recent diagnostic events for /status command."""
    recent = list(_recent)
    msg_events = [e for e in recent if e.type == "message"]
    usage_events = [e for e in recent if e.type == "usage"]
    loop_events = [e for e in recent if e.type == "tool_loop"]

    total_cost = sum(getattr(e, "cost", 0) for e in usage_events)
    total_messages = len([e for e in msg_events if getattr(e, "phase", "") == "completed"])
    avg_latency = 0
    latencies = [getattr(e, "latency_ms", 0) for e in usage_events if getattr(e, "latency_ms", 0) > 0]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)

    return {
        "total_events": len(recent),
        "messages_processed": total_messages,
        "total_cost_recent": round(total_cost, 4),
        "avg_latency_ms": round(avg_latency, 0),
        "loop_detections": len(loop_events),
        "models_used": list(set(getattr(e, "model", "") for e in usage_events if getattr(e, "model", ""))),
    }
