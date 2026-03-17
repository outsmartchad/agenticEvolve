"""Tests for gateway.redact."""
import pytest
from gateway.redact import redact, _mask_token, RedactingFilter


class TestMaskToken:
    def test_short_token(self):
        assert _mask_token("short") == "***"

    def test_long_token(self):
        token = "sk-proj-abcdefghijklmnop1234"
        result = _mask_token(token)
        assert result.startswith("sk-pro")
        assert result.endswith("1234")
        assert "..." in result


class TestRedact:
    def test_openai_key(self):
        text = "Using API key sk-proj-abcdefghijklmnopqrstuvwxyz1234"
        result = redact(text)
        assert "sk-pro" in result
        assert "abcdefghijklmnopqrst" not in result

    def test_env_assignment(self):
        text = "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234"
        result = redact(text)
        assert "abcdefghijklmnopqrst" not in result

    def test_github_pat(self):
        text = "token is ghp_abcdefghijklmnopqrstuvwxyz12"
        result = redact(text)
        assert "ghp_ab" in result
        assert "abcdefghijklmnopqrst" not in result

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.long.token"
        result = redact(text)
        assert "eyJhbG" in result
        assert "IkpXVCJ9" not in result

    def test_telegram_bot_token(self):
        text = "bot1234567890:AAFake_Token-ForTestingOnly_abcdef"
        result = redact(text)
        assert "AAFake_Token" not in result

    def test_pem_block(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...base64...\n-----END RSA PRIVATE KEY-----"
        result = redact(text)
        assert "BEGIN RSA PRIVATE KEY" in result
        assert "END RSA PRIVATE KEY" in result
        assert "redacted" in result

    def test_clean_text_unchanged(self):
        text = "Hello world, no secrets here"
        assert redact(text) == text

    def test_empty_text(self):
        assert redact("") == ""

    def test_json_field(self):
        text = '{"apiKey": "sk-abcdefghijklmnopqrstuvwxyz1234"}'
        result = redact(text)
        assert "abcdefghijklmnopqrst" not in result

    def test_groq_key(self):
        text = "gsk_abcdefghijklmnopqrstuvwxyz"
        result = redact(text)
        assert "abcdefghijklmnopqrst" not in result


class TestRedactingFilter:
    def test_filter_redacts_msg(self):
        import logging
        f = RedactingFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "key is sk-proj-abcdefghijklmnopqrstuvwxyz1234", (), None
        )
        f.filter(record)
        assert "abcdefghijklmnopqrst" not in record.msg
