"""Tests for gateway.context — context window management."""
import pytest

from gateway.context import (
    estimate_tokens,
    check_context_size,
    compact_history,
    auto_compact_if_needed,
)


class TestTokenEstimation:
    def test_basic(self):
        assert estimate_tokens("hello") > 0

    def test_proportional(self):
        short = estimate_tokens("hi")
        long = estimate_tokens("hello world this is a longer string")
        assert long > short


class TestCheckContextSize:
    def test_small_prompt_ok(self):
        r = check_context_size("hello world")
        assert r["ok"] is True
        assert r["action"] == "ok"

    def test_large_prompt_compact(self):
        # 60% of 200K tokens = 120K tokens = ~420K chars
        big = "x" * 420_000
        r = check_context_size(big)
        assert r["action"] == "compact"

    def test_huge_prompt_reject(self):
        # 85% of 200K tokens = 170K tokens = ~595K chars
        huge = "x" * 600_000
        r = check_context_size(huge)
        assert r["action"] == "reject"


class TestCompactHistory:
    def test_empty(self):
        assert compact_history([]) == []

    def test_short_history_unchanged(self):
        h = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = compact_history(h, target_chars=10000)
        assert len(result) == 2

    def test_long_history_compacted(self):
        h = [{"role": "user", "content": "msg " * 200} for _ in range(20)]
        result = compact_history(h, target_chars=2000)
        assert len(result) < 20
        total = sum(len(m["content"]) for m in result)
        assert total <= 3000  # some overhead allowed

    def test_keeps_first_and_last(self):
        h = [{"role": "user", "content": f"msg_{i}" * 50} for i in range(15)]
        result = compact_history(h, target_chars=2000)
        # First message should be present
        assert "msg_0" in result[0]["content"]
        # Last message should be present
        assert "msg_14" in result[-1]["content"]


class TestAutoCompact:
    def test_no_compact_needed(self):
        h = [{"role": "user", "content": "hi"}] * 12
        result = auto_compact_if_needed(h, "", "hello")
        assert result == h

    def test_compact_triggered(self):
        # Create history that would push context over 60% of 200K tokens.
        # _format_history caps formatted history at ~8K chars, so we need
        # session_context large enough to push total past 60% threshold
        # (60% of 200K tokens ≈ 420K chars at 3.5 chars/token).
        h = [{"role": "user", "content": "x" * 20000}] * 12
        result = auto_compact_if_needed(h, "x" * 420000, "hello")
        # Should be compacted
        total = sum(len(m["content"]) for m in result)
        assert total < sum(len(m["content"]) for m in h)
