"""Shared fixtures for agenticEvolve tests."""
import sys
from pathlib import Path

import pytest

# Ensure gateway package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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
