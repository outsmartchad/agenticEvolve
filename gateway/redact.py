"""Log redaction — strip secrets from logs and output.

Adapted from OpenClaw's redact.ts. Detects API keys, tokens, passwords,
PEM blocks, and common provider prefixes using regex patterns.
Masks tokens showing first 6 + last 4 chars.
"""
import logging
import re

log = logging.getLogger("agenticEvolve.redact")

MIN_TOKEN_LEN = 18
KEEP_START = 6
KEEP_END = 4

# ── Default redaction patterns ───────────────────────────────
_DEFAULT_PATTERNS_RAW = [
    # ENV-style assignments
    r'\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\b\s*[=:]\s*(["\']?)([^\s"\'\\]+)\1',
    # JSON fields
    r'"(?:apiKey|token|secret|password|passwd|accessToken|refreshToken)"\s*:\s*"([^"]+)"',
    # CLI flags
    r'--(?:api[-_]?key|token|secret|password|passwd)\s+(["\']?)([^\s"\']+)\1',
    # Authorization headers
    r'Authorization\s*[:=]\s*Bearer\s+([A-Za-z0-9._\-+=]+)',
    r'\bBearer\s+([A-Za-z0-9._\-+=]{18,})\b',
    # PEM blocks
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----',
    # Common provider token prefixes
    r'\b(sk-[A-Za-z0-9_-]{8,})\b',           # OpenAI
    r'\b(ghp_[A-Za-z0-9]{20,})\b',           # GitHub PAT
    r'\b(github_pat_[A-Za-z0-9_]{20,})\b',   # GitHub fine-grained PAT
    r'\b(xox[baprs]-[A-Za-z0-9-]{10,})\b',   # Slack
    r'\b(xapp-[A-Za-z0-9-]{10,})\b',         # Slack app
    r'\b(gsk_[A-Za-z0-9_-]{10,})\b',         # Groq
    r'\b(AIza[0-9A-Za-z\-_]{20,})\b',        # Google
    r'\b(pplx-[A-Za-z0-9_-]{10,})\b',        # Perplexity
    r'\b(npm_[A-Za-z0-9]{10,})\b',           # npm
    # Telegram bot tokens
    r'\bbot(\d{6,}:[A-Za-z0-9_-]{20,})\b',
    r'\b(\d{6,}:[A-Za-z0-9_-]{20,})\b',
]

DEFAULT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DEFAULT_PATTERNS_RAW]


def _mask_token(token: str) -> str:
    """Mask a token, preserving first 6 + last 4 chars."""
    if len(token) < MIN_TOKEN_LEN:
        return "***"
    return f"{token[:KEEP_START]}...{token[-KEEP_END:]}"


def _redact_pem(block: str) -> str:
    """Redact PEM private key block, keeping BEGIN/END lines."""
    lines = [l for l in block.splitlines() if l.strip()]
    if len(lines) < 2:
        return "***"
    return f"{lines[0]}\n...redacted...\n{lines[-1]}"


def _redact_match(m: re.Match) -> str:
    """Redact a single regex match."""
    full = m.group(0)

    # PEM blocks
    if "PRIVATE KEY-----" in full:
        return _redact_pem(full)

    # Find the last non-empty capture group (the actual token)
    groups = [g for g in m.groups() if g]
    token = groups[-1] if groups else full
    masked = _mask_token(token)

    if token == full:
        return masked
    return full.replace(token, masked)


def redact(text: str, patterns: list[re.Pattern] | None = None) -> str:
    """Redact secrets from text using regex patterns.

    Args:
        text: Text to redact.
        patterns: Custom patterns (defaults to DEFAULT_PATTERNS).

    Returns:
        Text with secrets masked.
    """
    if not text:
        return text

    pats = patterns or DEFAULT_PATTERNS
    result = text
    for pattern in pats:
        result = pattern.sub(_redact_match, result)
    return result


# ── Logging integration ──────────────────────────────────────

class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(str(v)) if isinstance(v, str) else v
                               for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact(str(a)) if isinstance(a, str) else a for a in record.args
                )
        return True
