"""Tests for env var sanitization in gateway.agent."""
import pytest

from gateway.agent import _sanitize_env, _BLOCKED_ENV_EXACT, _KEEP_ENV


class TestEnvSanitization:
    """Env var sanitization should block secrets, keep essentials."""

    def test_blocks_api_keys(self):
        env = {"ANTHROPIC_API_KEY": "sk-xxx", "OPENAI_API_KEY": "sk-yyy", "PATH": "/usr/bin"}
        result = _sanitize_env(env)
        assert "ANTHROPIC_API_KEY" not in result
        assert "OPENAI_API_KEY" not in result
        assert "PATH" in result

    def test_blocks_platform_tokens(self):
        env = {"TELEGRAM_BOT_TOKEN": "123:ABC", "DISCORD_BOT_TOKEN": "xyz", "HOME": "/Users/test"}
        result = _sanitize_env(env)
        assert "TELEGRAM_BOT_TOKEN" not in result
        assert "DISCORD_BOT_TOKEN" not in result
        assert "HOME" in result

    def test_blocks_aws_prefix(self):
        env = {"AWS_SECRET_ACCESS_KEY": "xxx", "AWS_REGION": "us-east-1", "PATH": "/usr/bin"}
        result = _sanitize_env(env)
        assert "AWS_SECRET_ACCESS_KEY" not in result
        assert "AWS_REGION" not in result

    def test_blocks_docker_prefix(self):
        env = {"DOCKER_HOST": "tcp://...", "USER": "test"}
        result = _sanitize_env(env)
        assert "DOCKER_HOST" not in result
        assert "USER" in result

    def test_keeps_essentials(self):
        env = {"PATH": "/usr/bin", "HOME": "/Users/test", "LANG": "en_US.UTF-8",
               "SHELL": "/bin/zsh", "TERM": "xterm", "USER": "test", "TMPDIR": "/tmp"}
        result = _sanitize_env(env)
        for k in env:
            assert k in result, f"{k} should be kept"

    def test_keeps_unknown_vars(self):
        env = {"MY_CUSTOM_VAR": "hello", "PATH": "/usr/bin"}
        result = _sanitize_env(env)
        assert "MY_CUSTOM_VAR" in result

    def test_empty_env(self):
        result = _sanitize_env({})
        assert result == {}

    def test_mutates_in_place(self):
        env = {"ANTHROPIC_API_KEY": "sk-xxx", "PATH": "/usr/bin"}
        result = _sanitize_env(env)
        assert result is env  # should mutate, not copy
