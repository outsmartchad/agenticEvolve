"""Tests for gateway/platforms/telegram.py — pure functions and static methods."""
import pytest

from gateway.platforms.telegram import TelegramAdapter


class TestParseFlags:
    """Tests for TelegramAdapter._parse_flags (static method, pure function)."""

    def test_bool_flag_present(self):
        args = ["--dry-run", "arg1"]
        result = TelegramAdapter._parse_flags(args, {
            "--dry-run": {"type": "bool"},
        })
        assert result["--dry-run"] is True
        assert args == ["arg1"]

    def test_bool_flag_absent(self):
        args = ["arg1"]
        result = TelegramAdapter._parse_flags(args, {
            "--dry-run": {"type": "bool"},
        })
        assert result["--dry-run"] is False
        assert args == ["arg1"]

    def test_bool_flag_with_alias(self):
        args = ["preview", "arg1"]
        result = TelegramAdapter._parse_flags(args, {
            "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
        })
        assert result["--dry-run"] is True
        assert args == ["arg1"]

    def test_value_flag(self):
        args = ["--model", "opus", "arg1"]
        result = TelegramAdapter._parse_flags(args, {
            "--model": {"type": "value"},
        })
        assert result["--model"] == "opus"
        assert args == ["arg1"]

    def test_value_flag_with_cast(self):
        args = ["--limit", "25"]
        result = TelegramAdapter._parse_flags(args, {
            "--limit": {"type": "value", "cast": int, "default": 10},
        })
        assert result["--limit"] == 25
        assert args == []

    def test_value_flag_missing_value(self):
        args = ["--limit"]
        result = TelegramAdapter._parse_flags(args, {
            "--limit": {"type": "value", "cast": int, "default": 10},
        })
        assert result["--limit"] == 10
        assert args == []

    def test_value_flag_invalid_cast(self):
        args = ["--limit", "notanumber"]
        result = TelegramAdapter._parse_flags(args, {
            "--limit": {"type": "value", "cast": int, "default": 10},
        })
        assert result["--limit"] == 10

    def test_value_flag_absent_uses_default(self):
        args = ["arg1"]
        result = TelegramAdapter._parse_flags(args, {
            "--model": {"type": "value", "default": "sonnet"},
        })
        assert result["--model"] == "sonnet"
        assert args == ["arg1"]

    def test_multiple_flags(self):
        args = ["--dry-run", "--model", "opus", "--limit", "5", "remaining"]
        result = TelegramAdapter._parse_flags(args, {
            "--dry-run": {"type": "bool"},
            "--model": {"type": "value"},
            "--limit": {"type": "value", "cast": int, "default": 10},
        })
        assert result["--dry-run"] is True
        assert result["--model"] == "opus"
        assert result["--limit"] == 5
        assert args == ["remaining"]

    def test_empty_args(self):
        args = []
        result = TelegramAdapter._parse_flags(args, {
            "--dry-run": {"type": "bool"},
            "--model": {"type": "value", "default": "sonnet"},
        })
        assert result["--dry-run"] is False
        assert result["--model"] == "sonnet"


class TestIsAllowed:
    """Tests for TelegramAdapter._is_allowed."""

    def test_allowed_user(self):
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.allowed_users = {"123", "456"}
        assert adapter._is_allowed(123) is True

    def test_denied_user(self):
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.allowed_users = {"123", "456"}
        assert adapter._is_allowed(789) is False

    def test_empty_allowlist_denies_all(self):
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.allowed_users = set()
        assert adapter._is_allowed(123) is False
