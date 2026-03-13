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
        CREATE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title) WHERE title IS NOT NULL;

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

        CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            platform TEXT,
            session_id TEXT,
            cost REAL NOT NULL,
            pipeline TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_costs_timestamp ON costs(timestamp);

        CREATE TABLE IF NOT EXISTS instincts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            context TEXT,
            confidence REAL DEFAULT 0.3,
            seen_count INTEGER DEFAULT 1,
            project_ids TEXT DEFAULT '[]',
            promoted_to TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_instincts_confidence ON instincts(confidence);
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
        """CREATE VIRTUAL TABLE instincts_fts USING fts5(
            pattern, context, content=instincts, content_rowid=id
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


HANDOFF_DIR = Path.home() / ".agenticEvolve" / "sessions"


def snapshot_session(session_id: str, handoff_note: str = "") -> Path:
    """Write a handoff snapshot for a session to a JSON file.

    Captures the last 10 messages so the next session can resume deterministically
    without relying on context that may have been compacted or lost.

    Args:
        session_id: Session to snapshot.
        handoff_note: Optional note appended to the snapshot (e.g. what was in progress).

    Returns:
        Path to the written handoff file.
    """
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT 10",
        (session_id,)
    ).fetchall()
    conn.close()

    # Reverse so messages are chronological
    last_messages = [dict(r) for r in reversed(rows)]

    payload = {
        "session_id": session_id,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "last_messages": last_messages,
        "handoff_note": handoff_note,
    }

    handoff_path = HANDOFF_DIR / f"{session_id}.handoff.json"
    handoff_path.write_text(json.dumps(payload, indent=2))
    return handoff_path


def load_handoff(session_id: str) -> dict | None:
    """Load a handoff snapshot for a session.

    Args:
        session_id: Session ID to load.

    Returns:
        Handoff dict, or None if no snapshot exists.
    """
    handoff_path = HANDOFF_DIR / f"{session_id}.handoff.json"
    if not handoff_path.exists():
        return None
    try:
        return json.loads(handoff_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def end_session(session_id: str, handoff_note: str = ""):
    """End a session, stamping ended_at and writing a handoff snapshot if warranted.

    A snapshot is written only when the session has more than 3 messages, to
    avoid noise from short pings and health-checks.

    Args:
        session_id: Session to end.
        handoff_note: Optional note captured in the handoff file.
    """
    conn = _connect()
    conn.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), session_id)
    )
    count_row = conn.execute(
        "SELECT message_count FROM sessions WHERE id = ?",
        (session_id,)
    ).fetchone()
    conn.commit()
    conn.close()

    # Write handoff snapshot for substantive sessions (> 3 messages)
    if count_row and (count_row["message_count"] or 0) > 3:
        snapshot_session(session_id, handoff_note=handoff_note)


def search_sessions(query: str, limit: int = 5,
                    time_decay_days: int = 30) -> list[dict]:
    """FTS5 search across all messages with time-decay weighting.

    Recent sessions are ranked higher. The decay weight halves every
    ``time_decay_days`` days, so a session from today scores 1.0 and one
    from 30 days ago scores ~0.5.

    Args:
        query: FTS5 query string.
        limit: Maximum number of unique sessions to return.
        time_decay_days: Half-life in days for recency weighting.
    """
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
    """, (query, limit * 5)).fetchall()  # over-fetch — will re-rank after decay
    conn.close()

    import math
    now = datetime.now(timezone.utc)

    # Group by session, apply time-decay to FTS rank
    seen: dict[str, dict] = {}
    for row in rows:
        sid = row["session_id"]

        # Parse session age and compute decay multiplier
        try:
            started = datetime.fromisoformat(row["started_at"])
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            days_ago = max(0.0, (now - started).total_seconds() / 86400)
        except (ValueError, TypeError):
            days_ago = time_decay_days  # treat unparseable as old

        # Decay: score * 2^(-days_ago / half_life) — higher is better
        # FTS5 rank is negative (lower = better match), so negate before applying decay
        decay = math.pow(2.0, -days_ago / time_decay_days)
        fts_score = -(row["rank"] or 0)  # negate so higher = better
        decayed_score = fts_score * decay

        if sid not in seen:
            seen[sid] = {
                "session_id": sid,
                "source": row["source"],
                "title": row["title"],
                "started_at": row["started_at"],
                "score": decayed_score,
                "matches": [],
            }
        else:
            seen[sid]["score"] = max(seen[sid]["score"], decayed_score)

        seen[sid]["matches"].append({
            "role": row["role"],
            "content": row["content"][:500],
            "timestamp": row["timestamp"],
        })

    # Sort by decayed score descending, take top N
    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:limit]
    # Remove internal score key before returning
    for r in results:
        r.pop("score", None)
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


# ── Cost tracking ────────────────────────────────────────────

def log_cost(cost: float, platform: str = "", session_id: str = "",
             pipeline: str = "") -> None:
    """Dual-write cost entry to SQLite. Complements the cost.log file."""
    conn = _connect()
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO costs (timestamp, platform, session_id, cost, pipeline) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, platform, session_id, cost, pipeline)
    )
    conn.commit()
    conn.close()


def get_cost_today() -> float:
    """Return total cost for the current UTC day from SQLite."""
    conn = _connect()
    row = conn.execute(
        "SELECT SUM(cost) FROM costs WHERE date(timestamp) = date('now')"
    ).fetchone()
    conn.close()
    return float(row[0] or 0)


def get_cost_week() -> float:
    """Return total cost for the current UTC week (Mon–Sun) from SQLite."""
    conn = _connect()
    row = conn.execute(
        "SELECT SUM(cost) FROM costs "
        "WHERE date(timestamp) >= date('now', 'weekday 1', '-7 days')"
    ).fetchone()
    conn.close()
    return float(row[0] or 0)


# ── Instincts ────────────────────────────────────────────────

def upsert_instinct(pattern: str, context: str = "", project_id: str = "",
                    confidence_delta: float = 0.05) -> int:
    """Insert or update an instinct, incrementing confidence on repeat observations.

    If an instinct with the same pattern already exists, increments seen_count,
    applies confidence_delta (capped at 1.0), and appends project_id if new.
    Otherwise inserts a fresh instinct at confidence 0.3.

    Args:
        pattern: The observed behaviour pattern (used as the dedup key).
        context: Optional context string (stage, tool, session type).
        project_id: Hash of the git remote URL for the project this was seen in.
        confidence_delta: How much to increase confidence on repeat observation.

    Returns:
        The instinct row ID.
    """
    conn = _connect()
    ts = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT id, confidence, seen_count, project_ids FROM instincts WHERE pattern = ?",
        (pattern,)
    ).fetchone()

    if existing:
        row_id = existing["id"]
        new_confidence = min(1.0, existing["confidence"] + confidence_delta)
        new_seen = existing["seen_count"] + 1

        # Append project_id if not already recorded
        try:
            projects = json.loads(existing["project_ids"] or "[]")
        except json.JSONDecodeError:
            projects = []
        if project_id and project_id not in projects:
            projects.append(project_id)

        conn.execute(
            "UPDATE instincts SET confidence=?, seen_count=?, project_ids=?, updated_at=? WHERE id=?",
            (new_confidence, new_seen, json.dumps(projects), ts, row_id)
        )
        # Sync FTS content
        conn.execute("DELETE FROM instincts_fts WHERE rowid=?", (row_id,))
        conn.execute(
            "INSERT INTO instincts_fts(rowid, pattern, context) VALUES (?, ?, ?)",
            (row_id, pattern, context or existing["context"] or "")
        )
    else:
        projects = [project_id] if project_id else []
        cursor = conn.execute(
            "INSERT INTO instincts (pattern, context, confidence, seen_count, "
            "project_ids, created_at, updated_at) VALUES (?, ?, 0.3, 1, ?, ?, ?)",
            (pattern, context, json.dumps(projects), ts, ts)
        )
        row_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO instincts_fts(rowid, pattern, context) VALUES (?, ?, ?)",
            (row_id, pattern, context or "")
        )

    conn.commit()
    conn.close()
    return row_id


def get_promotable_instincts(min_conf: float = 0.8,
                              min_projects: int = 2) -> list[dict]:
    """Return instincts that meet the promotion threshold.

    An instinct is promotable when it has been observed with sufficient
    confidence across enough distinct projects, and has not yet been promoted.

    Args:
        min_conf: Minimum confidence score (0.0–1.0). Default 0.8.
        min_projects: Minimum number of distinct projects. Default 2.

    Returns:
        List of instinct dicts ordered by confidence descending.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM instincts WHERE confidence >= ? AND promoted_to IS NULL "
        "ORDER BY confidence DESC",
        (min_conf,)
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        d = dict(row)
        try:
            projects = json.loads(d.get("project_ids") or "[]")
        except json.JSONDecodeError:
            projects = []
        if len(projects) >= min_projects:
            d["project_ids"] = projects
            results.append(d)

    return results


def score_and_route_observation(pattern: str, context: str = "",
                                project_id: str = "") -> str:
    """Score an observation by importance and route to the right store.

    Importance scale:
      5 — critical cross-project insight → upsert instinct + promote to MEMORY.md
      4 — strong single-project insight  → upsert instinct with high delta
      3 — useful pattern                 → upsert instinct with standard delta
      2 — weak/tentative signal          → upsert instinct with low delta
      1 — noise                          → discard

    Scoring heuristics (keyword-based, no LLM required):
      - High-signal words → score 4-5
      - Standard patterns → score 3
      - Short/vague → score 2
      - Single-word or filler → score 1

    Args:
        pattern: Observed behaviour pattern text.
        context: Optional context label (stage, tool, session type).
        project_id: Hash of git remote for project-scoped tracking.

    Returns:
        Routing decision: 'memory', 'instinct', 'instinct_weak', or 'discard'.
    """
    if not pattern or len(pattern.strip()) < 10:
        return "discard"

    text = pattern.lower()

    # High-signal keywords → score 4+
    high_signal = [
        "always", "never", "critical", "required", "must", "regression",
        "root cause", "workaround", "breaking", "security", "performance",
        "cross-project", "universal", "pattern",
    ]
    # Standard keywords → score 3
    standard_signal = [
        "prefer", "avoid", "when", "instead", "better", "useful",
        "workflow", "convention", "format", "output",
    ]

    score = 2  # default: weak
    if len(pattern.strip()) < 20:
        score = 1
    elif any(k in text for k in high_signal):
        score = 4 + (1 if sum(1 for k in high_signal if k in text) >= 3 else 0)
    elif any(k in text for k in standard_signal):
        score = 3

    if score <= 1:
        return "discard"
    elif score == 2:
        upsert_instinct(pattern, context=context, project_id=project_id,
                        confidence_delta=0.02)
        return "instinct_weak"
    elif score == 3:
        upsert_instinct(pattern, context=context, project_id=project_id,
                        confidence_delta=0.05)
        return "instinct"
    else:  # 4 or 5
        upsert_instinct(pattern, context=context, project_id=project_id,
                        confidence_delta=0.1)
        # Append high-importance observations to MEMORY.md
        mem_path = Path.home() / ".agenticEvolve" / "memory" / "MEMORY.md"
        if mem_path.exists():
            existing = mem_path.read_text()
            marker = "<!-- auto-instincts -->"
            entry = f"\n§\n{pattern}"
            if marker in existing:
                mem_path.write_text(existing.replace(marker, entry + "\n" + marker))
            else:
                mem_path.write_text(existing + entry)
        return "memory"


def mark_instinct_promoted(instinct_id: int, promoted_to: str) -> None:
    """Stamp an instinct as promoted to a skill, command, or agent.

    Args:
        instinct_id: Row ID of the instinct to promote.
        promoted_to: Promotion target label — 'skill', 'command', or 'agent'.
    """
    conn = _connect()
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE instincts SET promoted_to=?, updated_at=? WHERE id=?",
        (promoted_to, ts, instinct_id)
    )
    conn.commit()
    conn.close()


# Initialize on import
init_db()
