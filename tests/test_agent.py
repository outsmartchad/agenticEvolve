"""Tests for gateway/agent.py — pure functions and LoopDetector."""
import pytest

from gateway.agent import (
    _format_history,
    _classify_stderr,
    generate_title,
    LoopDetector,
    InvokeFailReason,
)


# ── _classify_stderr ─────────────────────────────────────────


class TestClassifyStderr:
    def test_auth_permanent_invalid_key(self):
        assert _classify_stderr("Error: invalid api key") == InvokeFailReason.AUTH_PERMANENT

    def test_auth_permanent_unauthorized(self):
        assert _classify_stderr("401 Unauthorized") == InvokeFailReason.AUTH_PERMANENT

    def test_billing(self):
        assert _classify_stderr("quota exceeded for this billing period") == InvokeFailReason.BILLING

    def test_billing_payment(self):
        assert _classify_stderr("payment required") == InvokeFailReason.BILLING

    def test_rate_limit_429(self):
        assert _classify_stderr("HTTP 429 Too Many Requests") == InvokeFailReason.RATE_LIMIT

    def test_rate_limit_text(self):
        assert _classify_stderr("rate limit exceeded") == InvokeFailReason.RATE_LIMIT

    def test_unknown(self):
        assert _classify_stderr("some random error") == InvokeFailReason.UNKNOWN

    def test_empty(self):
        assert _classify_stderr("") == InvokeFailReason.UNKNOWN

    def test_case_insensitive(self):
        assert _classify_stderr("INVALID API KEY") == InvokeFailReason.AUTH_PERMANENT


# ── _format_history ──────────────────────────────────────────


class TestFormatHistory:
    def test_empty_history(self):
        assert _format_history([]) == ""

    def test_single_message(self):
        result = _format_history([{"role": "user", "content": "hello"}])
        assert "[user]: hello" in result

    def test_preserves_order(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        result = _format_history(history)
        assert result.index("first") < result.index("second") < result.index("third")

    def test_respects_max_turns(self):
        history = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
        result = _format_history(history, max_turns=5)
        # Should only include last 5 messages
        assert "msg 25" in result
        assert "msg 29" in result
        assert "msg 0" not in result

    def test_compaction_on_large_input(self):
        """History exceeding max_chars should be compacted."""
        history = [
            {"role": "user", "content": "X" * 3000},
            {"role": "assistant", "content": "Y" * 3000},
            {"role": "user", "content": "Z" * 3000},
        ]
        result = _format_history(history, max_chars=2000)
        assert len(result) <= 2000

    def test_tool_result_stripping(self):
        """Large messages with code fences should be stripped in pass 2."""
        history = [
            {"role": "assistant", "content": "Here is output:\n```\n" + "A" * 600 + "\n```"},
            {"role": "user", "content": "thanks"},
        ]
        result = _format_history(history, max_chars=500)
        assert len(result) <= 500


# ── generate_title ───────────────────────────────────────────


class TestGenerateTitle:
    def test_short_message(self):
        assert generate_title("hello world") == "hello world"

    def test_long_message_truncated(self):
        msg = "A" * 100
        title = generate_title(msg)
        assert len(title) <= 60
        assert title.endswith("...")

    def test_strips_whitespace(self):
        assert generate_title("  hello  ") == "hello"

    def test_replaces_newlines(self):
        assert generate_title("line1\nline2") == "line1 line2"


# ── LoopDetector ─────────────────────────────────────────────


class TestLoopDetector:
    def test_first_call_returns_1(self):
        ld = LoopDetector()
        count = ld.record("s1", [{"name": "Read", "input": {"path": "/a"}}])
        assert count == 1

    def test_identical_calls_increment(self):
        ld = LoopDetector()
        tools = [{"name": "Bash", "input": {"command": "ls"}}]
        ld.record("s1", tools)
        ld.record("s1", tools)
        count = ld.record("s1", tools)
        assert count == 3

    def test_different_calls_reset_count(self):
        ld = LoopDetector()
        ld.record("s1", [{"name": "Read", "input": {"path": "/a"}}])
        ld.record("s1", [{"name": "Read", "input": {"path": "/a"}}])
        count = ld.record("s1", [{"name": "Write", "input": {"path": "/b"}}])
        assert count == 1

    def test_different_sessions_isolated(self):
        ld = LoopDetector()
        tools = [{"name": "Bash", "input": {"command": "ls"}}]
        ld.record("s1", tools)
        ld.record("s1", tools)
        count = ld.record("s2", tools)
        assert count == 1  # s2 is independent

    def test_reset_clears_session(self):
        ld = LoopDetector()
        tools = [{"name": "Bash", "input": {"command": "ls"}}]
        ld.record("s1", tools)
        ld.record("s1", tools)
        ld.reset("s1")
        count = ld.record("s1", tools)
        assert count == 1

    def test_fingerprint_order_independent(self):
        """Two tool calls in different order should produce same fingerprint."""
        ld = LoopDetector()
        tools_a = [
            {"name": "Read", "input": {"path": "/a"}},
            {"name": "Bash", "input": {"command": "ls"}},
        ]
        tools_b = [
            {"name": "Bash", "input": {"command": "ls"}},
            {"name": "Read", "input": {"path": "/a"}},
        ]
        ld.record("s1", tools_a)
        count = ld.record("s1", tools_b)
        assert count == 2  # same fingerprint despite different order

    def test_maxlen_respected(self):
        ld = LoopDetector(maxlen=3)
        tools = [{"name": "Read", "input": {"path": "/a"}}]
        other = [{"name": "Write", "input": {"path": "/b"}}]
        # Fill deque with "other" to push out old entries
        ld.record("s1", other)
        ld.record("s1", other)
        ld.record("s1", other)
        # Now add "tools" — deque should have dropped oldest "other"
        count = ld.record("s1", tools)
        assert count == 1
