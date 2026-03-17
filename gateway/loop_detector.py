"""Tool loop detection — prevents runaway agent sessions from burning tokens.

Adapted from OpenClaw's tool-loop-detection.ts. Monitors tool call patterns
from claude -p output and detects:
1. generic_repeat: same tool+args called N times in window
2. known_poll_no_progress: poll/status calls returning identical results
3. ping_pong: alternating between two tool calls with no progress
4. global_circuit_breaker: hard stop at N identical no-progress calls
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum

log = logging.getLogger("agenticEvolve.loop_detector")

# ── Configuration ────────────────────────────────────────────
HISTORY_SIZE = 30
WARNING_THRESHOLD = 10
CRITICAL_THRESHOLD = 20
GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30

# Known polling tool names (from claude -p output)
KNOWN_POLL_TOOLS = frozenset({
    "command_status", "Read", "Bash",
})


class Severity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class DetectionMode(StrEnum):
    GENERIC_REPEAT = "generic_repeat"
    KNOWN_POLL = "known_poll_no_progress"
    PING_PONG = "ping_pong"
    GLOBAL_BREAKER = "global_circuit_breaker"


@dataclass
class ToolCallEntry:
    tool_name: str
    args_hash: str
    result_hash: str | None = None
    call_id: str = ""
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class LoopDetection:
    stuck: bool
    mode: DetectionMode
    level: Severity
    count: int
    message: str
    warning_key: str = ""


# ── Hashing ──────────────────────────────────────────────────

def _stable_json(obj: object) -> str:
    """Deterministic JSON serialization (sorted keys)."""
    try:
        return json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        return str(obj)


def hash_tool_call(tool_name: str, params: dict | str | None = None) -> str:
    """Hash a tool call by name + deterministic params."""
    param_str = _stable_json(params) if params else ""
    digest = hashlib.sha256(param_str.encode()).hexdigest()[:16]
    return f"{tool_name}:{digest}"


def hash_result(result: str | None, error: str | None = None) -> str:
    """Hash a tool call result/error."""
    if error:
        content = f"error:{error}"
    else:
        # Truncate long results to avoid hashing megabytes
        content = (result or "")[:2000]
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# ── Loop Detector State ──────────────────────────────────────

class LoopDetectorState:
    """Per-session tool loop detection state."""

    def __init__(
        self,
        history_size: int = HISTORY_SIZE,
        warning_threshold: int = WARNING_THRESHOLD,
        critical_threshold: int = CRITICAL_THRESHOLD,
        global_breaker_threshold: int = GLOBAL_CIRCUIT_BREAKER_THRESHOLD,
    ):
        self.history: list[ToolCallEntry] = []
        self.history_size = history_size
        self.warning_threshold = warning_threshold
        self.critical_threshold = max(critical_threshold, warning_threshold + 1)
        self.global_breaker_threshold = max(global_breaker_threshold, self.critical_threshold + 1)
        self._warned_keys: set[str] = set()

    def record_call(self, tool_name: str, args_hash: str, call_id: str = "") -> None:
        """Record a tool call (before execution)."""
        entry = ToolCallEntry(
            tool_name=tool_name,
            args_hash=args_hash,
            call_id=call_id,
        )
        self.history.append(entry)
        if len(self.history) > self.history_size:
            self.history = self.history[-self.history_size:]

    def record_outcome(self, tool_name: str, args_hash: str, result_hash: str,
                        call_id: str = "") -> None:
        """Record a tool call outcome (after execution)."""
        # Walk backwards to find matching entry
        for entry in reversed(self.history):
            if entry.result_hash is not None:
                continue
            if call_id and entry.call_id == call_id:
                entry.result_hash = result_hash
                return
            if entry.tool_name == tool_name and entry.args_hash == args_hash:
                entry.result_hash = result_hash
                return
        # No match — append new entry
        self.history.append(ToolCallEntry(
            tool_name=tool_name, args_hash=args_hash,
            result_hash=result_hash, call_id=call_id,
        ))
        if len(self.history) > self.history_size:
            self.history = self.history[-self.history_size:]

    def _no_progress_streak(self) -> int:
        """Count consecutive identical (tool, args, result) from the tail."""
        if not self.history:
            return 0
        last = self.history[-1]
        if last.result_hash is None:
            return 0
        count = 0
        for entry in reversed(self.history):
            if (entry.tool_name == last.tool_name
                    and entry.args_hash == last.args_hash
                    and entry.result_hash == last.result_hash):
                count += 1
            else:
                break
        return count

    def _repeat_count(self, tool_name: str, args_hash: str) -> int:
        """Count occurrences of (tool, args) in the window."""
        return sum(1 for e in self.history
                   if e.tool_name == tool_name and e.args_hash == args_hash)

    def _ping_pong_streak(self) -> tuple[int, str | None]:
        """Detect A-B-A-B alternation from the tail. Returns (count, paired_key)."""
        if len(self.history) < 4:
            return 0, None

        # Find two most recent distinct signatures
        sigs: list[str] = []
        for entry in reversed(self.history):
            sig = f"{entry.tool_name}:{entry.args_hash}"
            if sig not in sigs:
                sigs.append(sig)
                if len(sigs) == 2:
                    break
        if len(sigs) < 2:
            return 0, None

        # Check alternating pattern from tail
        a, b = sigs[0], sigs[1]
        expected = a
        count = 0
        for entry in reversed(self.history):
            sig = f"{entry.tool_name}:{entry.args_hash}"
            if sig == expected:
                count += 1
                expected = b if expected == a else a
            else:
                break

        # Check no-progress evidence: all results for each sig are identical
        a_results = set()
        b_results = set()
        for entry in self.history[-count:] if count > 0 else []:
            sig = f"{entry.tool_name}:{entry.args_hash}"
            if entry.result_hash:
                (a_results if sig == a else b_results).add(entry.result_hash)

        no_progress = len(a_results) <= 1 and len(b_results) <= 1
        pair_key = "|".join(sorted([a, b]))
        return (count if no_progress else 0), pair_key

    def detect(self, tool_name: str, args_hash: str) -> LoopDetection | None:
        """Detect tool call loop patterns. Returns detection or None if clean."""
        is_poll = tool_name in KNOWN_POLL_TOOLS
        streak = self._no_progress_streak()

        # 1. Global circuit breaker (highest priority)
        if streak >= self.global_breaker_threshold:
            key = f"global:{tool_name}:{args_hash}"
            return LoopDetection(
                stuck=True, mode=DetectionMode.GLOBAL_BREAKER,
                level=Severity.CRITICAL, count=streak,
                message=f"Global circuit breaker: {tool_name} called {streak} times with no progress. Session halted.",
                warning_key=key,
            )

        # 2. Known poll no-progress
        if is_poll:
            if streak >= self.critical_threshold:
                key = f"poll_crit:{tool_name}:{args_hash}"
                return LoopDetection(
                    stuck=True, mode=DetectionMode.KNOWN_POLL,
                    level=Severity.CRITICAL, count=streak,
                    message=f"Poll loop critical: {tool_name} returned identical results {streak} times. Stopping.",
                    warning_key=key,
                )
            if streak >= self.warning_threshold:
                key = f"poll_warn:{tool_name}:{args_hash}"
                if key in self._warned_keys:
                    return None
                self._warned_keys.add(key)
                return LoopDetection(
                    stuck=True, mode=DetectionMode.KNOWN_POLL,
                    level=Severity.WARNING, count=streak,
                    message=f"Poll loop warning: {tool_name} returned identical results {streak} times. Consider increasing wait time or trying a different approach.",
                    warning_key=key,
                )

        # 3. Ping-pong detection
        pp_count, pp_key = self._ping_pong_streak()
        if pp_count >= self.critical_threshold:
            return LoopDetection(
                stuck=True, mode=DetectionMode.PING_PONG,
                level=Severity.CRITICAL, count=pp_count,
                message=f"Ping-pong loop critical: alternating tool calls {pp_count} times with no progress. Stopping.",
                warning_key=f"pp:{pp_key}",
            )
        if pp_count >= self.warning_threshold:
            key = f"pp:{pp_key}"
            if key not in self._warned_keys:
                self._warned_keys.add(key)
                return LoopDetection(
                    stuck=True, mode=DetectionMode.PING_PONG,
                    level=Severity.WARNING, count=pp_count,
                    message=f"Ping-pong loop warning: alternating tool calls {pp_count} times. Try a different approach.",
                    warning_key=key,
                )

        # 4. Generic repeat (non-poll tools only)
        if not is_poll:
            repeat = self._repeat_count(tool_name, args_hash)
            if repeat >= self.warning_threshold:
                key = f"repeat:{tool_name}:{args_hash}"
                if key not in self._warned_keys:
                    self._warned_keys.add(key)
                    return LoopDetection(
                        stuck=True, mode=DetectionMode.GENERIC_REPEAT,
                        level=Severity.WARNING, count=repeat,
                        message=f"Repeat warning: {tool_name} called {repeat} times with same args. Consider a different approach.",
                        warning_key=key,
                    )

        return None

    def get_stats(self) -> dict:
        """Get tool call statistics for monitoring."""
        if not self.history:
            return {"total_calls": 0}

        tool_counts: dict[str, int] = {}
        for entry in self.history:
            tool_counts[entry.tool_name] = tool_counts.get(entry.tool_name, 0) + 1

        return {
            "total_calls": len(self.history),
            "unique_tools": len(tool_counts),
            "tool_counts": tool_counts,
            "no_progress_streak": self._no_progress_streak(),
        }
