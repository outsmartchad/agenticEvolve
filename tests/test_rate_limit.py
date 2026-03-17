"""Tests for gateway.rate_limit — per-user sliding-window rate limiter."""
import time
from unittest.mock import patch

import pytest

from gateway.rate_limit import RateLimiter


class TestRateLimiter:
    """Basic rate limiter functionality."""

    def test_allows_first_request(self):
        rl = RateLimiter()
        allowed, reason = rl.check("user1")
        assert allowed is True
        assert reason == ""

    def test_allows_within_limit(self):
        rl = RateLimiter({"rate_limit": {"per_user_per_minute": 3}})
        for i in range(3):
            allowed, _ = rl.check("user1")
            assert allowed is True
            rl.record("user1")

    def test_blocks_over_limit(self):
        rl = RateLimiter({"rate_limit": {"per_user_per_minute": 2, "cooldown_seconds": 10}})
        rl.record("user1")
        rl.record("user1")
        allowed, reason = rl.check("user1")
        assert allowed is False
        assert "2/min" in reason

    def test_different_users_independent(self):
        rl = RateLimiter({"rate_limit": {"per_user_per_minute": 1}})
        rl.record("user1")
        allowed, _ = rl.check("user1")
        assert allowed is False
        allowed2, _ = rl.check("user2")
        assert allowed2 is True

    def test_chat_rate_limit(self):
        rl = RateLimiter({"rate_limit": {"per_user_per_minute": 100, "per_chat_per_minute": 2}})
        rl.record("user1", "group1")
        rl.record("user2", "group1")
        allowed, reason = rl.check("user3", "group1")
        assert allowed is False
        assert "chat" in reason.lower()

    def test_status(self):
        rl = RateLimiter()
        rl.record("user1")
        s = rl.status("user1")
        assert "per_minute" in s
        assert "per_hour" in s

    def test_prune_stale(self):
        rl = RateLimiter()
        rl.record("user1")
        rl.prune_stale()  # should not crash

    def test_default_config(self):
        rl = RateLimiter()
        assert rl.per_user_per_minute == 5
        assert rl.per_user_per_hour == 30

    def test_custom_config(self):
        rl = RateLimiter({"rate_limit": {"per_user_per_minute": 10, "per_user_per_hour": 50}})
        assert rl.per_user_per_minute == 10
        assert rl.per_user_per_hour == 50
