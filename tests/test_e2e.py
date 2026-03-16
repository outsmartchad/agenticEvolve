"""End-to-end integration tests that call `claude -p` for real.

Skipped when the CLI is not installed (CI) and excluded from normal runs
via the ``e2e`` marker — run explicitly with ``pytest -m e2e``.
"""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.agent import invoke_claude

_HAS_CLAUDE = shutil.which("claude") is not None


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_CLAUDE, reason="claude CLI not installed")
def test_invoke_claude_basic():
    """A simple arithmetic prompt should succeed and return '4'."""
    result = invoke_claude(
        "What is 2+2? Reply with just the number.",
        model="sonnet",
        max_seconds=30,
    )
    assert result["success"] is True, f"invoke_claude failed: {result.get('text')}"
    assert "4" in result["text"], f"Expected '4' in response, got: {result['text']}"
    assert result["cost"] > 0, f"Expected positive cost, got: {result['cost']}"


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_CLAUDE, reason="claude CLI not installed")
def test_invoke_claude_timeout():
    """An impossibly short timeout should cause a failure / timeout response."""
    result = invoke_claude(
        (
            "Write a 5000-word essay about the complete history of mathematics "
            "from ancient Babylon to modern category theory. Include every major "
            "mathematician and their contributions."
        ),
        model="sonnet",
        max_seconds=1,
    )
    # The function should report failure — either success=False from
    # subprocess.TimeoutExpired or from empty output due to early kill.
    assert result["success"] is False, (
        f"Expected failure on 1s timeout, but got success=True: {result.get('text', '')[:200]}"
    )


# ── Platform routing: Telegram → on_message → Claude response ────────


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_CLAUDE, reason="claude CLI not installed")
def test_telegram_message_routes_to_claude(tmp_path, monkeypatch):
    """Simulate a Telegram text message being routed through on_message to Claude.

    Validates the full path: inbound message → session lookup → invoke_claude → reply.
    This is the highest-value routing path — if it breaks, the bot goes silent.
    """
    from gateway.run import GatewayRunner
    import gateway.session_db as sdb

    # Isolate DB
    p = tmp_path / "e2e_sessions.db"
    monkeypatch.setattr(sdb, "DB_PATH", p)
    sdb.init_db()

    # Minimal config — no Telegram token needed, just enough to init runner
    cfg = {
        "model": "sonnet",
        "daily_cost_cap": 999999,
        "weekly_cost_cap": 999999,
        "session_idle_minutes": 120,
        "autonomy": "full",
        "platforms": {
            "telegram": {"enabled": True, "allowed_users": [1]},
        },
    }
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = cfg
    runner._active_sessions = {}
    runner._session_last_active = {}
    runner._session_msg_count = {}
    runner._locks = {}
    runner._cost_strikes = 0
    runner._cost_backoff_until = 0.0
    runner._pending_images = {}

    result = runner.on_message(
        message="What is 3+3? Reply with just the number.",
        platform="telegram",
        user_id="1",
        session_id=None,
    )

    assert isinstance(result, str), f"on_message should return str, got {type(result)}"
    assert "6" in result, f"Expected '6' in Claude's response, got: {result[:200]}"


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_CLAUDE, reason="claude CLI not installed")
def test_trace_id_logged_on_evolve_invoke(tmp_path, monkeypatch):
    """Verify trace_id appears in the audit table after an _invoke call.

    Uses a mocked invoke_claude_streaming so no real LLM call is made.
    """
    import gateway.session_db as sdb
    from gateway.evolve import EvolveOrchestrator

    # Isolate DB
    p = tmp_path / "trace_test.db"
    monkeypatch.setattr(sdb, "DB_PATH", p)
    sdb.init_db()

    # Patch invoke_claude_streaming to avoid real API call
    import gateway.agent as agent_mod
    monkeypatch.setattr(
        agent_mod, "invoke_claude_streaming",
        lambda *a, **kw: {"text": "[]", "cost": 0.001, "success": True},
    )

    orch = EvolveOrchestrator(model="sonnet", on_progress=lambda _: None)
    trace_id = orch.trace_id

    # Trigger a single stage invocation
    orch._invoke("Analyze this: []", "ANALYZE")

    # Audit table should have an entry for this trace_id
    conn = sdb._connect()
    rows = conn.execute(
        "SELECT stage, action, result FROM audit WHERE trace_id = ?", (trace_id,)
    ).fetchall()
    conn.close()

    assert len(rows) >= 1, f"Expected audit entries for trace_id {trace_id}, got 0"
    assert rows[0]["stage"] == "ANALYZE"
    assert rows[0]["action"] == "invoke_claude"
