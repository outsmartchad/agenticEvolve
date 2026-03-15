"""Tests for gateway/run.py — cron parser, session management, cost cap."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from gateway.run import GatewayRunner


class TestCronNextRun:
    """Tests for GatewayRunner._next_cron_run — cron expression parser."""

    @pytest.fixture()
    def runner(self):
        r = GatewayRunner()
        r.config = {"cron": {"enabled": True}}
        return r

    def _job(self, cron, tz=""):
        return {"cron": cron, "timezone": tz}

    def test_every_minute(self, runner):
        after = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        nxt = runner._next_cron_run(self._job("* * * * *"), after)
        assert nxt == datetime(2026, 3, 15, 10, 1, 0, tzinfo=timezone.utc)

    def test_specific_minute(self, runner):
        after = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        nxt = runner._next_cron_run(self._job("30 * * * *"), after)
        assert nxt.minute == 30
        assert nxt.hour == 10

    def test_specific_hour_and_minute(self, runner):
        after = datetime(2026, 3, 15, 8, 0, 0, tzinfo=timezone.utc)
        nxt = runner._next_cron_run(self._job("15 14 * * *"), after)
        assert nxt.hour == 14
        assert nxt.minute == 15

    def test_wraps_to_next_day(self, runner):
        after = datetime(2026, 3, 15, 23, 30, 0, tzinfo=timezone.utc)
        nxt = runner._next_cron_run(self._job("0 8 * * *"), after)
        assert nxt.day == 16
        assert nxt.hour == 8
        assert nxt.minute == 0

    def test_step_expression(self, runner):
        after = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        nxt = runner._next_cron_run(self._job("*/15 * * * *"), after)
        assert nxt.minute == 15
        assert nxt.hour == 10

    @pytest.mark.xfail(reason="Cron parser doesn't support range expressions (9-17) yet")
    def test_range_expression(self, runner):
        after = datetime(2026, 3, 15, 5, 0, 0, tzinfo=timezone.utc)
        nxt = runner._next_cron_run(self._job("0 9-17 * * *"), after)
        assert nxt.hour == 9
        assert nxt.minute == 0


class TestSessionKey:
    def test_session_key_format(self):
        r = GatewayRunner()
        key = r._session_key("telegram", "12345")
        assert key == "telegram:12345"


class TestCostCap:
    def test_within_cap_allowed(self):
        r = GatewayRunner()
        r.config = {"daily_cost_cap": 100.0, "weekly_cost_cap": 500.0}
        with patch("gateway.run.get_today_cost", return_value=5.0), \
             patch("gateway.agent.get_week_cost", return_value=20.0):
            allowed, reason = r._check_cost_cap()
            assert allowed is True
            assert reason == ""

    def test_daily_cap_exceeded(self):
        r = GatewayRunner()
        r.config = {"daily_cost_cap": 10.0, "weekly_cost_cap": 500.0}
        with patch("gateway.run.get_today_cost", return_value=15.0), \
             patch("gateway.agent.get_week_cost", return_value=20.0):
            allowed, reason = r._check_cost_cap()
            assert allowed is False
            assert "Daily cost cap" in reason

    def test_weekly_cap_exceeded(self):
        r = GatewayRunner()
        r.config = {"daily_cost_cap": 999.0, "weekly_cost_cap": 10.0}
        with patch("gateway.run.get_today_cost", return_value=5.0), \
             patch("gateway.agent.get_week_cost", return_value=15.0):
            allowed, reason = r._check_cost_cap()
            assert allowed is False
            assert "Weekly cost cap" in reason
