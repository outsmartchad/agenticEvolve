"""Scan agent output for leaked secrets from .env and known patterns.

Defence-in-depth layer: even if Claude reads .env and outputs a token,
this module catches it before it reaches the user. Works alongside
redact.py (which catches pattern-based secrets) by also checking
against actual .env values — including base64 and URL-encoded variants.
"""

import os
import re
import base64
import urllib.parse
import logging
from pathlib import Path

log = logging.getLogger("agenticEvolve.credential_guard")


class LeakMatch:
    """A single detected credential leak."""

    def __init__(self, secret_name: str, match_type: str, position: int):
        self.secret_name = secret_name
        self.match_type = match_type  # "raw", "base64", "url_encoded"
        self.position = position

    def __repr__(self) -> str:
        return f"LeakMatch({self.secret_name!r}, {self.match_type!r}, pos={self.position})"


class LeakDetector:
    """Detect and redact leaked secrets from agent output.

    Loads secrets from a .env file and/or manual registration, then scans
    text for raw, base64-encoded, and URL-encoded variants.
    """

    # Key name substrings that indicate a value is a secret
    _SECRET_KEY_HINTS = frozenset({
        "token", "key", "secret", "password", "api", "auth",
        "credential", "passwd", "private",
    })

    def __init__(self, env_path: Path | None = None, min_secret_len: int = 8):
        self._secrets: dict[str, str] = {}  # name -> value
        self._min_secret_len = min_secret_len
        if env_path:
            self._load_env(env_path)

    def _load_env(self, path: Path) -> None:
        """Load secrets from .env file."""
        if not path.exists():
            log.debug(f"credential_guard: .env not found at {path}")
            return
        loaded = 0
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            # Only track values that look like secrets
            key_lower = key.lower()
            if (any(sk in key_lower for sk in self._SECRET_KEY_HINTS)
                    and len(value) >= self._min_secret_len):
                self._secrets[key] = value
                loaded += 1
        if loaded:
            log.info(f"credential_guard: tracking {loaded} secrets from .env")

    def add_secret(self, name: str, value: str) -> None:
        """Manually add a secret to track."""
        if len(value) >= self._min_secret_len:
            self._secrets[name] = value

    @property
    def secret_count(self) -> int:
        """Number of secrets being tracked."""
        return len(self._secrets)

    def scan(self, text: str) -> list[LeakMatch]:
        """Scan text for leaked secrets. Returns list of matches."""
        if not text or not self._secrets:
            return []

        matches = []
        for name, value in self._secrets.items():
            # Raw value check
            if value in text:
                pos = text.index(value)
                matches.append(LeakMatch(name, "raw", pos))
                continue

            # Base64-encoded check
            try:
                b64 = base64.b64encode(value.encode()).decode()
                if len(b64) >= 12 and b64 in text:
                    matches.append(LeakMatch(name, "base64", text.index(b64)))
                    continue
            except Exception:
                pass

            # URL-encoded check
            url_enc = urllib.parse.quote(value)
            if url_enc != value and url_enc in text:
                matches.append(LeakMatch(name, "url_encoded", text.index(url_enc)))

        return matches

    def redact_leaks(self, text: str) -> tuple[str, list[LeakMatch]]:
        """Scan and redact any leaked secrets. Returns (redacted_text, matches).

        Order of operations: scan first to get match list, then replace all
        variants (raw, base64, url_encoded) for each secret.
        """
        matches = self.scan(text)
        if not matches:
            return text, []

        result = text
        for name, value in self._secrets.items():
            # Replace raw value
            if value in result:
                result = result.replace(value, f"[REDACTED:{name}]")

            # Replace base64-encoded value
            try:
                b64 = base64.b64encode(value.encode()).decode()
                if len(b64) >= 12 and b64 in result:
                    result = result.replace(b64, f"[REDACTED:{name}:b64]")
            except Exception:
                pass

            # Replace URL-encoded value
            url_enc = urllib.parse.quote(value)
            if url_enc != value and url_enc in result:
                result = result.replace(url_enc, f"[REDACTED:{name}:url]")

        return result, matches
