"""End-to-end integration tests that call `claude -p` for real.

Skipped when the CLI is not installed (CI) and excluded from normal runs
via the ``e2e`` marker — run explicitly with ``pytest -m e2e``.
"""
import shutil

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
