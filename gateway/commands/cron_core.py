"""Shared cron storage helpers — used by both CLI and gateway Telegram mixin."""
import json
import re
from pathlib import Path

EXODIR = Path.home() / ".agenticEvolve"
CRON_DIR = EXODIR / "cron"
CRON_JOBS_FILE = CRON_DIR / "jobs.json"


def load_cron_jobs() -> list[dict]:
    if CRON_JOBS_FILE.exists():
        try:
            return json.loads(CRON_JOBS_FILE.read_text())
        except Exception:
            return []
    return []


def save_cron_jobs(jobs: list[dict]) -> None:
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))


def parse_interval(s: str) -> int | None:
    """Parse interval string like '5m', '2h', '1d' to seconds."""
    m = re.match(r"^(\d+)\s*(s|sec|m|min|h|hr|hour|d|day)s?$", s.lower())
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit in ("s", "sec"):
        return n
    if unit in ("m", "min"):
        return n * 60
    if unit in ("h", "hr", "hour"):
        return n * 3600
    if unit in ("d", "day"):
        return n * 86400
    return None
