"""SQLite session persistence with FTS5 full-text search."""
import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".agenticEvolve" / "memory" / "sessions.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            user_id TEXT,
            title TEXT,
            model TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            message_count INTEGER DEFAULT 0,
            token_count_in INTEGER DEFAULT 0,
            token_count_out INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL,
            content TEXT,
            timestamp TEXT NOT NULL,
            token_count INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title) WHERE title IS NOT NULL;

        CREATE TABLE IF NOT EXISTS learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            target_type TEXT NOT NULL,
            verdict TEXT NOT NULL,
            patterns TEXT,
            operational_benefit TEXT,
            skill_created TEXT,
            full_report TEXT,
            cost REAL DEFAULT 0,
            created_at TEXT NOT NULL
        );
    """)
    # FTS5 — ignore errors if already exists
    for stmt in [
        """CREATE VIRTUAL TABLE messages_fts USING fts5(
            content, content=messages, content_rowid=id
        )""",
        """CREATE VIRTUAL TABLE learnings_fts USING fts5(
            target, patterns, operational_benefit, full_report,
            content=learnings, content_rowid=id
        )""",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # already exists
    conn.commit()
    conn.close()


def create_session(session_id: str, source: str, user_id: str = None,
                   model: str = "sonnet") -> str:
    conn = _connect()
    conn.execute(
        "INSERT INTO sessions (id, source, user_id, model, started_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, source, user_id, model, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()
    return session_id


def generate_session_id() -> str:
    now = datetime.now(timezone.utc)
    hex_suffix = os.urandom(4).hex()
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{hex_suffix}"


def add_message(session_id: str, role: str, content: str, token_count: int = 0):
    conn = _connect()
    ts = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, token_count) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, ts, token_count)
    )
    rowid = cursor.lastrowid
    # Update FTS
    if content:
        conn.execute(
            "INSERT INTO messages_fts(rowid, content) VALUES (?, ?)",
            (rowid, content)
        )
    # Update session counters
    conn.execute(
        "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
        (session_id,)
    )
    if role == "user":
        conn.execute(
            "UPDATE sessions SET token_count_in = token_count_in + ? WHERE id = ?",
            (token_count, session_id)
        )
    elif role == "assistant":
        conn.execute(
            "UPDATE sessions SET token_count_out = token_count_out + ? WHERE id = ?",
            (token_count, session_id)
        )
    conn.commit()
    conn.close()


def end_session(session_id: str):
    conn = _connect()
    conn.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), session_id)
    )
    conn.commit()
    conn.close()


def search_sessions(query: str, limit: int = 5) -> list[dict]:
    """FTS5 search across all messages. Returns matching sessions with context."""
    conn = _connect()
    rows = conn.execute("""
        SELECT m.session_id, m.role, m.content, m.timestamp,
               s.source, s.title, s.started_at,
               rank
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.id
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit * 3)).fetchall()  # over-fetch then dedupe by session
    conn.close()

    # Group by session, take top N unique sessions
    seen = {}
    for row in rows:
        sid = row["session_id"]
        if sid not in seen:
            seen[sid] = {
                "session_id": sid,
                "source": row["source"],
                "title": row["title"],
                "started_at": row["started_at"],
                "matches": []
            }
        seen[sid]["matches"].append({
            "role": row["role"],
            "content": row["content"][:500],
            "timestamp": row["timestamp"]
        })

    results = list(seen.values())[:limit]
    return results


def set_title(session_id: str, title: str):
    conn = _connect()
    conn.execute(
        "UPDATE sessions SET title = ? WHERE id = ? AND title IS NULL",
        (title, session_id)
    )
    conn.commit()
    conn.close()


def list_sessions(source: str = None, limit: int = 20) -> list[dict]:
    conn = _connect()
    if source:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE source = ? ORDER BY started_at DESC LIMIT ?",
            (source, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_messages(session_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats() -> dict:
    conn = _connect()
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    sources = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM sessions GROUP BY source"
    ).fetchall()
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    conn.close()
    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "sources": {r["source"]: r["cnt"] for r in sources},
        "db_size_mb": round(db_size / 1024 / 1024, 1)
    }


# ── Learnings ────────────────────────────────────────────────

def add_learning(target: str, target_type: str, verdict: str,
                 patterns: str = "", operational_benefit: str = "",
                 skill_created: str = "", full_report: str = "",
                 cost: float = 0) -> int:
    """Store a /learn finding. Returns the learning ID."""
    conn = _connect()
    ts = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO learnings (target, target_type, verdict, patterns, "
        "operational_benefit, skill_created, full_report, cost, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (target, target_type, verdict, patterns, operational_benefit,
         skill_created, full_report, cost, ts)
    )
    rowid = cursor.lastrowid
    # Update FTS
    conn.execute(
        "INSERT INTO learnings_fts(rowid, target, patterns, operational_benefit, full_report) "
        "VALUES (?, ?, ?, ?, ?)",
        (rowid, target, patterns, operational_benefit, full_report)
    )
    conn.commit()
    conn.close()
    return rowid


def search_learnings(query: str, limit: int = 5) -> list[dict]:
    """FTS5 search across learnings."""
    conn = _connect()
    rows = conn.execute(
        "SELECT l.id, l.target, l.target_type, l.verdict, l.patterns, "
        "l.operational_benefit, l.skill_created, l.cost, l.created_at, rank "
        "FROM learnings_fts "
        "JOIN learnings l ON learnings_fts.rowid = l.id "
        "WHERE learnings_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_learnings(limit: int = 20) -> list[dict]:
    """List recent learnings."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, target, target_type, verdict, patterns, skill_created, "
        "cost, created_at FROM learnings ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Initialize on import
init_db()
