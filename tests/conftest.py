"""Shared fixtures for agenticEvolve tests."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

# Ensure gateway package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Custom markers ──────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests that call real external services")


# ── Autouse: isolate session_db to a tmp DB for every test ──────────
@pytest.fixture(autouse=True)
def _isolate_session_db(tmp_path, monkeypatch):
    """Redirect session_db.DB_PATH to a per-test temp DB for all tests.

    Prevents test pollution of the real ~/.agenticEvolve/memory/sessions.db
    and ensures persistent dedup (signal_urls table) is isolated per test.
    """
    import gateway.session_db as sdb

    p = tmp_path / "isolated_sessions.db"
    monkeypatch.setattr(sdb, "DB_PATH", p)
    sdb.init_db()
    yield


@pytest.fixture()
def signals_dir(tmp_path: Path) -> Path:
    """Create a temporary signals directory."""
    d = tmp_path / "signals"
    d.mkdir()
    return d


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch):
    """Override session_db.DB_PATH to an isolated temp DB.

    Returns the Path to the temp database file.
    """
    import gateway.session_db as sdb

    p = tmp_path / "test_sessions.db"
    monkeypatch.setattr(sdb, "DB_PATH", p)
    sdb.init_db()
    return p


# ── Telegram mock fixtures for command handler testing ──────────


@pytest.fixture()
def mock_update():
    """Create a mock Telegram Update object with common defaults."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 934847281
    update.message.chat_id = 934847281
    update.message.chat.id = 934847281
    update.message.text = ""
    update.message.caption = None
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    update.message.reply_voice = AsyncMock()
    update.message.reply_photo = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    return update


@pytest.fixture()
def mock_context():
    """Create a mock Telegram Context object."""
    ctx = MagicMock()
    ctx.args = []
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.edit_message_text = AsyncMock()
    ctx.bot.send_photo = AsyncMock()
    ctx.bot.get_file = AsyncMock()
    return ctx


@pytest.fixture()
def mock_gateway():
    """Create a mock GatewayRunner with config and session state."""
    gw = MagicMock()
    gw.config = {
        "model": "sonnet",
        "daily_cost_cap": 999999,
        "weekly_cost_cap": 999999,
        "session_idle_minutes": 120,
        "autonomy": "full",
        "auto_approve_skills": True,
        "cron": {"enabled": True},
        "tts": {"mode": "inbound", "voice": "en-US-AndrewMultilingualNeural"},
        "platforms": {
            "telegram": {"enabled": True, "allowed_users": [934847281]},
            "discord": {"enabled": False},
            "whatsapp": {"enabled": False},
        },
    }
    gw._active_sessions = {}
    gw._session_last_active = {}
    gw._session_msg_count = {}
    gw._locks = {}
    gw._start_time = 1710460800.0  # 2024-03-15 00:00:00 UTC
    gw._log_cost = MagicMock()
    gw.pop_pending_images = MagicMock(return_value=[])
    return gw


@pytest.fixture()
def adapter(mock_gateway, tmp_path, monkeypatch):
    """Create a TelegramAdapter instance with mocked dependencies.

    Patches EXODIR in all mixin modules to use a temp directory.
    Sets up the adapter with allowed users and a mock gateway.
    """
    pytest.importorskip("telegram")
    from gateway.platforms.telegram import TelegramAdapter

    # Create adapter without calling __init__ (avoids needing real token)
    a = TelegramAdapter.__new__(TelegramAdapter)
    a.allowed_users = {"934847281"}
    a._gateway = mock_gateway
    a._user_lang = {}
    a._user_lang_loaded = True
    a.app = MagicMock()
    a.app.bot = MagicMock()
    a.app.bot.send_message = AsyncMock()
    a.app.bot.edit_message_text = AsyncMock()
    a.on_message = AsyncMock(return_value="Claude response here.")

    # Set up temp EXODIR structure
    exo = tmp_path / ".agenticEvolve"
    mem_dir = exo / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "MEMORY.md").write_text("# Memory\nTest memory content.\n")
    (mem_dir / "USER.md").write_text("# User\nTest user profile.\n")
    (exo / "SOUL.md").write_text("# Soul\nI am a test agent.\n")

    cron_dir = exo / "cron"
    cron_dir.mkdir(parents=True)
    (cron_dir / "jobs.json").write_text("[]")

    signals_dir = exo / "signals"
    signals_dir.mkdir(parents=True)

    config_file = exo / "config.yaml"
    config_file.write_text("model: sonnet\n")

    skills_queue = exo / "skills-queue"
    skills_queue.mkdir(parents=True)

    # Patch EXODIR in all mixin modules
    import gateway.commands.admin as admin_mod
    import gateway.commands.cron as cron_mod
    import gateway.commands.signals as signals_mod
    import gateway.commands.pipelines as pipelines_mod
    import gateway.commands.approval as approval_mod
    import gateway.commands.search as search_mod
    import gateway.commands.media as media_mod
    import gateway.commands.misc as misc_mod

    for mod in [admin_mod, cron_mod, signals_mod, pipelines_mod,
                approval_mod, search_mod, media_mod, misc_mod]:
        monkeypatch.setattr(mod, "EXODIR", exo)
        if hasattr(mod, "CRON_DIR"):
            monkeypatch.setattr(mod, "CRON_DIR", cron_dir)
        if hasattr(mod, "CRON_JOBS_FILE"):
            monkeypatch.setattr(mod, "CRON_JOBS_FILE", cron_dir / "jobs.json")

    return a


@pytest.fixture()
def denied_update():
    """Create a mock Update with an unauthorized user."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 999999  # Not in allowed_users
    update.message.chat_id = 999999
    update.message.reply_text = AsyncMock()
    return update
