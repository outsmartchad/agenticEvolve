"""Tests for gateway.credential_guard — leak detection and redaction."""
import base64
import urllib.parse
import pytest
from pathlib import Path

from gateway.credential_guard import LeakDetector, LeakMatch


class TestLeakDetectorInit:
    """Initialization and .env loading."""

    def test_loads_secrets_from_env(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "OPENAI_API_KEY=sk-proj-abcdef12345678\n"
            "TELEGRAM_BOT_TOKEN=1234567890:AAFakeTokenForTesting\n"
            "MODEL=sonnet\n"  # not a secret key name
        )
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 2

    def test_ignores_short_values(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("API_KEY=short\n")
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 0

    def test_ignores_non_secret_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "MODEL=sonnet\n"
            "LOG_LEVEL=DEBUG\n"
            "PORT=8080\n"
        )
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 0

    def test_handles_missing_env(self, tmp_path):
        ld = LeakDetector(env_path=tmp_path / "nonexistent.env")
        assert ld.secret_count == 0

    def test_handles_no_env_path(self):
        ld = LeakDetector(env_path=None)
        assert ld.secret_count == 0

    def test_strips_quotes_from_values(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "API_KEY='sk-proj-abcdef12345678'\n"
            'AUTH_TOKEN="tok_abcdefghijklmnop"\n'
        )
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 2
        # Values should be stripped of quotes
        matches = ld.scan("sk-proj-abcdef12345678")
        assert len(matches) == 1

    def test_skips_comments_and_blanks(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "# This is a comment\n"
            "\n"
            "API_KEY=sk-proj-abcdef12345678\n"
            "# Another comment\n"
        )
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 1

    def test_skips_lines_without_equals(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "not-a-valid-line\n"
            "API_KEY=sk-proj-abcdef12345678\n"
        )
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 1


class TestAddSecret:
    """Manual secret registration."""

    def test_add_secret(self):
        ld = LeakDetector()
        ld.add_secret("MY_TOKEN", "abcdefghijklmnop")
        assert ld.secret_count == 1

    def test_add_secret_ignores_short(self):
        ld = LeakDetector()
        ld.add_secret("MY_TOKEN", "short")
        assert ld.secret_count == 0

    def test_add_multiple_secrets(self):
        ld = LeakDetector()
        ld.add_secret("TOKEN_A", "abcdefghijklmnop")
        ld.add_secret("TOKEN_B", "1234567890abcdef")
        assert ld.secret_count == 2


class TestScanRaw:
    """Raw secret detection."""

    def test_detects_raw_secret(self):
        ld = LeakDetector()
        ld.add_secret("MY_KEY", "sk-proj-abcdef12345678")
        matches = ld.scan("Here is the key: sk-proj-abcdef12345678")
        assert len(matches) == 1
        assert matches[0].secret_name == "MY_KEY"
        assert matches[0].match_type == "raw"

    def test_clean_text_returns_empty(self):
        ld = LeakDetector()
        ld.add_secret("MY_KEY", "sk-proj-abcdef12345678")
        matches = ld.scan("Hello world, nothing suspicious here")
        assert matches == []

    def test_empty_text_returns_empty(self):
        ld = LeakDetector()
        ld.add_secret("MY_KEY", "sk-proj-abcdef12345678")
        matches = ld.scan("")
        assert matches == []

    def test_no_secrets_returns_empty(self):
        ld = LeakDetector()
        matches = ld.scan("any text at all")
        assert matches == []

    def test_multiple_secrets_detected(self):
        ld = LeakDetector()
        ld.add_secret("KEY_A", "first_secret_value_12345")
        ld.add_secret("KEY_B", "second_secret_value_67890")
        text = "Found first_secret_value_12345 and second_secret_value_67890"
        matches = ld.scan(text)
        assert len(matches) == 2
        names = {m.secret_name for m in matches}
        assert names == {"KEY_A", "KEY_B"}

    def test_position_is_correct(self):
        ld = LeakDetector()
        secret = "sk-proj-abcdef12345678"
        ld.add_secret("MY_KEY", secret)
        text = f"prefix {secret} suffix"
        matches = ld.scan(text)
        assert matches[0].position == text.index(secret)


class TestScanBase64:
    """Base64-encoded secret detection."""

    def test_detects_base64_encoded(self):
        ld = LeakDetector()
        secret = "sk-proj-abcdef12345678"
        ld.add_secret("MY_KEY", secret)
        b64 = base64.b64encode(secret.encode()).decode()
        text = f"Encoded: {b64}"
        matches = ld.scan(text)
        assert len(matches) == 1
        assert matches[0].match_type == "base64"

    def test_ignores_short_base64(self):
        """Base64 of short values (<12 chars encoded) should not match."""
        ld = LeakDetector()
        # 8-char secret → 12-char base64 (borderline)
        secret = "12345678"
        ld.add_secret("SHORT", secret)
        b64 = base64.b64encode(secret.encode()).decode()
        assert len(b64) == 12  # exactly at threshold
        text = f"data: {b64}"
        matches = ld.scan(text)
        # 12 chars is >= 12 so it should still match
        assert len(matches) == 1


class TestScanUrlEncoded:
    """URL-encoded secret detection."""

    def test_detects_url_encoded(self):
        ld = LeakDetector()
        secret = "my secret/token+value=123"
        ld.add_secret("MY_KEY", secret)
        url_enc = urllib.parse.quote(secret)
        assert url_enc != secret  # should differ (spaces, slashes, etc.)
        text = f"param={url_enc}"
        matches = ld.scan(text)
        assert len(matches) == 1
        assert matches[0].match_type == "url_encoded"

    def test_skips_url_encoding_when_same(self):
        """If url_encode(value) == value, it's the same as raw — no duplicate."""
        ld = LeakDetector()
        secret = "abcdefghijklmnop"  # no special chars
        ld.add_secret("MY_KEY", secret)
        text = f"val={secret}"
        matches = ld.scan(text)
        # Should match as raw, not URL-encoded
        assert len(matches) == 1
        assert matches[0].match_type == "raw"


class TestRedactLeaks:
    """Redaction of leaked secrets."""

    def test_redacts_raw_secret(self):
        ld = LeakDetector()
        secret = "sk-proj-abcdef12345678"
        ld.add_secret("OPENAI_KEY", secret)
        text = f"The key is {secret} and that's it"
        redacted, matches = ld.redact_leaks(text)
        assert secret not in redacted
        assert "[REDACTED:OPENAI_KEY]" in redacted
        assert len(matches) == 1

    def test_redacts_base64_secret(self):
        ld = LeakDetector()
        secret = "sk-proj-abcdef12345678"
        ld.add_secret("API_KEY", secret)
        b64 = base64.b64encode(secret.encode()).decode()
        text = f"encoded: {b64}"
        redacted, matches = ld.redact_leaks(text)
        assert b64 not in redacted
        assert "[REDACTED:API_KEY:b64]" in redacted

    def test_redacts_url_encoded_secret(self):
        ld = LeakDetector()
        secret = "my+secret/token=value123"
        ld.add_secret("AUTH_TOKEN", secret)
        url_enc = urllib.parse.quote(secret)
        text = f"?token={url_enc}"
        redacted, matches = ld.redact_leaks(text)
        assert url_enc not in redacted
        assert "[REDACTED:AUTH_TOKEN:url]" in redacted

    def test_clean_text_unchanged(self):
        ld = LeakDetector()
        ld.add_secret("KEY", "abcdefghijklmnop")
        text = "Nothing secret here"
        redacted, matches = ld.redact_leaks(text)
        assert redacted == text
        assert matches == []

    def test_multiple_secrets_redacted(self):
        ld = LeakDetector()
        ld.add_secret("KEY_A", "first_secret_value_12345")
        ld.add_secret("KEY_B", "second_secret_value_67890")
        text = "Keys: first_secret_value_12345 and second_secret_value_67890"
        redacted, matches = ld.redact_leaks(text)
        assert "first_secret_value_12345" not in redacted
        assert "second_secret_value_67890" not in redacted
        assert "[REDACTED:KEY_A]" in redacted
        assert "[REDACTED:KEY_B]" in redacted
        assert len(matches) == 2

    def test_redact_preserves_surrounding_text(self):
        ld = LeakDetector()
        secret = "sk-proj-abcdef12345678"
        ld.add_secret("KEY", secret)
        text = f"before {secret} after"
        redacted, _ = ld.redact_leaks(text)
        assert redacted == "before [REDACTED:KEY] after"


class TestLeakDetectorFromEnv:
    """Integration test: load from .env file and scan."""

    def test_full_flow(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "OPENAI_API_KEY=sk-proj-test1234567890abcdef\n"
            "TELEGRAM_BOT_TOKEN=9876543210:AABBCCDDEEFFtest_token_here\n"
            "MODEL=sonnet\n"
        )
        ld = LeakDetector(env_path=env)
        assert ld.secret_count == 2

        # Simulate agent output that leaks the OpenAI key
        output = "I found your key: sk-proj-test1234567890abcdef in the .env file"
        redacted, matches = ld.redact_leaks(output)
        assert "sk-proj-test1234567890abcdef" not in redacted
        assert "[REDACTED:OPENAI_API_KEY]" in redacted
        assert len(matches) == 1
        assert matches[0].secret_name == "OPENAI_API_KEY"

    def test_custom_min_length(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("API_KEY=short12\n")  # 7 chars
        ld_default = LeakDetector(env_path=env)
        assert ld_default.secret_count == 0  # too short for default min_secret_len=8

        ld_custom = LeakDetector(env_path=env, min_secret_len=5)
        assert ld_custom.secret_count == 1


class TestLeakMatch:
    """LeakMatch data class."""

    def test_repr(self):
        m = LeakMatch("MY_KEY", "raw", 42)
        assert "MY_KEY" in repr(m)
        assert "raw" in repr(m)
        assert "42" in repr(m)
