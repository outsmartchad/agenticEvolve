"""Tests for config validation (Phase 4)."""
import pytest
from gateway.config import validate_config


class TestConfigValidation:
    def test_empty_config_valid(self):
        errors = validate_config({})
        assert errors == []

    def test_valid_config(self):
        errors = validate_config({
            "model": "sonnet",
            "daily_cost_cap": 10.0,
            "weekly_cost_cap": 50.0,
            "platforms": {
                "telegram": {"enabled": True, "allowed_users": [123]},
            },
        })
        assert errors == []

    def test_negative_cost_cap(self):
        errors = validate_config({"daily_cost_cap": -5})
        assert any("daily_cost_cap" in e for e in errors)

    def test_string_cost_cap(self):
        errors = validate_config({"daily_cost_cap": "ten"})
        assert any("daily_cost_cap" in e for e in errors)

    def test_invalid_exec_security(self):
        errors = validate_config({"exec": {"security": "invalid"}})
        assert any("exec.security" in e for e in errors)

    def test_valid_exec_security(self):
        for val in ("deny", "allowlist", "full"):
            errors = validate_config({"exec": {"security": val}})
            assert not any("exec.security" in e for e in errors)

    def test_invalid_exec_ask(self):
        errors = validate_config({"exec": {"ask": "maybe"}})
        assert any("exec.ask" in e for e in errors)

    def test_valid_exec_ask(self):
        for val in ("off", "on-miss", "always"):
            errors = validate_config({"exec": {"ask": val}})
            assert not any("exec.ask" in e for e in errors)

    def test_invalid_exec_mode(self):
        errors = validate_config({"exec": {"mode": "docker"}})
        assert any("exec.mode" in e for e in errors)

    def test_valid_exec_mode(self):
        for val in ("sandbox", "gateway"):
            errors = validate_config({"exec": {"mode": val}})
            assert not any("exec.mode" in e for e in errors)

    def test_invalid_platform_config(self):
        errors = validate_config({"platforms": {"telegram": "bad"}})
        assert any("telegram" in e for e in errors)

    def test_invalid_allowed_users(self):
        errors = validate_config({
            "platforms": {"telegram": {"allowed_users": "not_a_list"}}
        })
        assert any("allowed_users" in e for e in errors)

    def test_invalid_rate_limit(self):
        errors = validate_config({
            "rate_limit": {"per_user_per_minute": -1}
        })
        assert any("per_user_per_minute" in e for e in errors)

    def test_model_not_string(self):
        errors = validate_config({"model": 123})
        assert any("model" in e for e in errors)
