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

        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_name TEXT,
            target_type TEXT NOT NULL DEFAULT 'channel',
            mode TEXT NOT NULL DEFAULT 'subscribe',
            created_at TEXT NOT NULL,
            UNIQUE(user_id, platform, target_id, mode)
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id, mode);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_platform ON subscriptions(platform, mode);

        CREATE TABLE IF NOT EXISTS platform_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            sender_name TEXT,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            message_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pm_platform_chat ON platform_messages(platform, chat_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_pm_timestamp ON platform_messages(timestamp);
    """)
    # Migrations: add columns/indexes to existing tables (idempotent)
    for stmt in [
        "ALTER TABLE platform_messages ADD COLUMN message_id TEXT",
        "CREATE INDEX IF NOT EXISTS idx_pm_message_id ON platform_messages(platform, message_id)",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column/index already exists

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
    # Migration: signal_urls dedup table (idempotent)
    for stmt in [
        """CREATE TABLE IF NOT EXISTS signal_urls (
            url TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_signal_urls_expires ON signal_urls(expires_at)",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # already exists

    # Migration: audit log table (idempotent)
    for stmt in [
        """CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            stage TEXT NOT NULL,
            action TEXT NOT NULL,
            user_id TEXT,
            result TEXT,
            metadata TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_audit_trace_id ON audit(trace_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_stage ON audit(stage, timestamp)",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # already exists

    conn.commit()
    conn.close()


def generate_trace_id() -> str:
    """Generate a unique trace ID for pipeline correlation."""
    now = datetime.now(timezone.utc)
    return f"tr_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"


def log_audit(
    trace_id: str,
    stage: str,
    action: str,
    result: str = None,
    user_id: str = None,
    metadata: dict | None = None,
):
    """Append an audit event to the audit table.

    Args:
        trace_id: Pipeline correlation ID from generate_trace_id().
        stage: Pipeline stage name (e.g. "COLLECT", "BUILD", "APPROVE").
        action: What happened (e.g. "skill_built", "skill_approved", "skill_rejected").
        result: "ok" | "fail" | free-form outcome string.
        user_id: Acting user (None for automated pipeline events).
        metadata: Arbitrary JSON-serialisable dict for extra context.
    """
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO audit (trace_id, timestamp, stage, action, user_id, result, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                trace_id,
                datetime.now(timezone.utc).isoformat(),
                stage,
                action,
                user_id,
                result,
                json.dumps(metadata) if metadata else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def signal_url_seen(url: str, ttl_days: int = 7) -> bool:
    """Return True if this URL was seen within the last ttl_days.

    Inserts the URL if unseen (or expired). Cleans up expired rows on each call.
    """
    from datetime import timedelta
    conn = _connect()
    try:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(days=ttl_days)).isoformat()

        # Purge expired entries (cheap, indexed)
        conn.execute("DELETE FROM signal_urls WHERE expires_at <= ?", (now.isoformat(),))

        row = conn.execute(
            "SELECT url FROM signal_urls WHERE url = ?", (url,)
        ).fetchone()

        if row:
            conn.commit()
            return True

        conn.execute(
            "INSERT INTO signal_urls (url, first_seen, expires_at) VALUES (?, ?, ?)",
            (url, now.isoformat(), expires),
        )
        conn.commit()
        return False
    finally:
        conn.close()


def get_user_pref(user_id: str, key: str, default: str = None) -> str | None:
    """Get a user preference value."""
    conn = _connect()
    row = conn.execute(
        "SELECT value FROM user_prefs WHERE user_id = ? AND key = ?",
        (user_id, key)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_user_pref(user_id: str, key: str, value: str):
    """Set a user preference value (upsert)."""
    conn = _connect()
    conn.execute(
        "INSERT INTO user_prefs (user_id, key, value, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (user_id, key, value, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def delete_user_pref(user_id: str, key: str):
    """Delete a user preference."""
    conn = _connect()
    conn.execute("DELETE FROM user_prefs WHERE user_id = ? AND key = ?", (user_id, key))
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
        "SELECT id, confidence, seen_count, project_ids, context FROM instincts WHERE pattern = ?",
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


def auto_promote_instincts(max_promotions: int = 3) -> list[str]:
    """Auto-promote high-confidence instincts to MEMORY.md.

    Finds instincts with confidence >= 0.8 across 2+ projects (or seen 5+ times)
    and appends them to MEMORY.md if there's room under the 2200 char limit.

    Returns list of promoted pattern strings.
    """
    # Relax the min_projects requirement — also promote if seen many times
    candidates = get_promotable_instincts(min_conf=0.8, min_projects=1)

    # Filter: either 2+ projects or seen 5+ times
    eligible = []
    for c in candidates:
        projects = c.get("project_ids", [])
        if len(projects) >= 2 or c.get("seen_count", 0) >= 5:
            eligible.append(c)

    if not eligible:
        return []

    mem_path = Path.home() / ".agenticEvolve" / "memory" / "MEMORY.md"
    if not mem_path.exists():
        return []

    existing = mem_path.read_text()
    char_limit = 2200
    promoted = []

    for inst in eligible[:max_promotions]:
        pattern = inst["pattern"]
        entry = f"\n§ [auto] {pattern}"

        # Check if pattern is already in MEMORY.md (substring match)
        if pattern[:50] in existing:
            mark_instinct_promoted(inst["id"], "memory_duplicate")
            continue

        # Check char budget
        if len(existing) + len(entry) > char_limit:
            break

        existing += entry
        promoted.append(pattern)
        mark_instinct_promoted(inst["id"], "memory")

    if promoted:
        mem_path.write_text(existing)
        import logging
        logging.getLogger("agenticEvolve.instincts").info(
            f"Auto-promoted {len(promoted)} instincts to MEMORY.md"
        )

    return promoted


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


# ── Running Sessions Search ──────────────────────────────────

def search_active_session(session_id: str, query: str,
                          limit: int = 10) -> list[dict]:
    """Search messages within a specific active session.

    Queries the raw messages table (not FTS) for the given session_id,
    filtering by substring match. This gives real-time access to the
    current conversation — including messages added seconds ago.

    Args:
        session_id: The session to search within.
        query: Substring to match (case-insensitive).
        limit: Max results to return.

    Returns:
        List of matching message dicts with role, content snippet, timestamp.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM messages "
        "WHERE session_id = ? AND content LIKE ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, f"%{query}%", limit)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"][:500],
             "timestamp": r["timestamp"], "source": "active_session"} for r in rows]


def get_active_session_context(session_id: str, last_n: int = 5) -> list[dict]:
    """Get the most recent messages from an active session.

    Used for injecting current session awareness into search results.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM messages "
        "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, last_n)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"][:500],
             "timestamp": r["timestamp"]} for r in reversed(rows)]


# ── Memory Search ────────────────────────────────────────────

def search_memory(query: str) -> list[dict]:
    """Parse §-delimited entries from MEMORY.md and match by substring.

    Memory is small enough (2200 chars max) that in-memory filtering
    is faster than any index. Returns matching entries with their
    position index.

    Args:
        query: Substring to match (case-insensitive).

    Returns:
        List of dicts with entry text, index, and source tag.
    """
    mem_path = Path.home() / ".agenticEvolve" / "memory" / "MEMORY.md"
    if not mem_path.exists():
        return []

    content = mem_path.read_text()
    entries = [e.strip() for e in content.split("§") if e.strip()]
    query_lower = query.lower()

    results = []
    for i, entry in enumerate(entries):
        if query_lower in entry.lower():
            results.append({
                "content": entry[:500],
                "index": i,
                "source": "memory",
            })
    return results


def search_user_profile(query: str) -> list[dict]:
    """Search USER.md entries by substring match."""
    user_path = Path.home() / ".agenticEvolve" / "memory" / "USER.md"
    if not user_path.exists():
        return []

    content = user_path.read_text()
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    query_lower = query.lower()

    results = []
    for line in lines:
        if query_lower in line.lower():
            results.append({
                "content": line[:300],
                "source": "user_profile",
            })
    return results


# ── Instincts Search ────────────────────────────────────────

def search_instincts(query: str, limit: int = 10) -> list[dict]:
    """FTS5 search across instincts table.

    Args:
        query: FTS5 query string.
        limit: Max results.

    Returns:
        List of instinct dicts with source tag.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT i.id, i.pattern, i.context, i.confidence, i.seen_count, "
        "i.project_ids, i.created_at, rank "
        "FROM instincts_fts "
        "JOIN instincts i ON instincts_fts.rowid = i.id "
        "WHERE instincts_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit)
    ).fetchall()
    conn.close()
    return [{
        "content": r["pattern"],
        "context": r["context"],
        "confidence": r["confidence"],
        "seen_count": r["seen_count"],
        "source": "instinct",
    } for r in rows]


# ── Cross-Layer Unified Search ───────────────────────────────

def unified_search(query: str, session_id: str = "",
                   limit_per_layer: int = 3) -> list[dict]:
    """Query all memory layers and merge results with source tags.

    Searches five layers in parallel:
      1. Sessions FTS (past conversations)
      2. Learnings FTS (absorbed knowledge)
      3. Instincts FTS (observed patterns)
      4. MEMORY.md (agent notes, §-delimited)
      5. USER.md (user profile)

    Each result is tagged with its source so the caller (or the agent)
    knows where the knowledge came from.

    Args:
        query: Search query string.
        session_id: If provided, also searches the current active session.
        limit_per_layer: Max results per layer (total will be up to 5x this).

    Returns:
        List of dicts, each with at minimum: content, source.
        Sorted by relevance within each layer, then interleaved.
    """
    results = []

    # 1. Sessions FTS — past conversations
    try:
        sessions = search_sessions(query, limit=limit_per_layer)
        for s in sessions:
            # Flatten session matches into individual results
            best_match = s.get("matches", [{}])[0] if s.get("matches") else {}
            results.append({
                "content": best_match.get("content", "")[:400],
                "session_title": s.get("title", ""),
                "session_date": (s.get("started_at") or "")[:10],
                "source": "session",
            })
    except Exception:
        pass

    # 2. Learnings FTS — absorbed knowledge
    try:
        learnings = search_learnings(query, limit=limit_per_layer)
        for l in learnings:
            results.append({
                "content": (l.get("patterns") or l.get("operational_benefit") or "")[:400],
                "target": l.get("target", ""),
                "verdict": l.get("verdict", ""),
                "source": "learning",
            })
    except Exception:
        pass

    # 3. Instincts FTS — observed patterns
    try:
        instincts = search_instincts(query, limit=limit_per_layer)
        for inst in instincts:
            results.append({
                "content": inst["content"][:400],
                "confidence": inst.get("confidence", 0),
                "seen_count": inst.get("seen_count", 0),
                "source": "instinct",
            })
    except Exception:
        pass

    # 4. MEMORY.md — agent notes
    try:
        mem_results = search_memory(query)
        for m in mem_results[:limit_per_layer]:
            results.append(m)
    except Exception:
        pass

    # 5. USER.md — user profile
    try:
        user_results = search_user_profile(query)
        for u in user_results[:limit_per_layer]:
            results.append(u)
    except Exception:
        pass

    # 6. Active session — current conversation (if session_id provided)
    if session_id:
        try:
            active = search_active_session(session_id, query, limit=limit_per_layer)
            results.extend(active)
        except Exception:
            pass

    # 7. Semantic search — TF-IDF cosine similarity (catches non-keyword matches)
    try:
        from .semantic import semantic_search
        semantic_results = semantic_search(query, top_k=limit_per_layer)
        # Only add semantic results that aren't already in FTS results (by content prefix)
        existing_prefixes = {r.get("content", "")[:80] for r in results}
        for sr in semantic_results:
            if sr["content"][:80] not in existing_prefixes:
                sr["source"] = f"semantic:{sr['source']}"  # tag as semantic match
                results.append(sr)
    except Exception:
        pass

    return results


def format_recall_context(results: list[dict], max_chars: int = 2000) -> str:
    """Format unified search results into a context block for the system prompt.

    Groups results by source and formats them concisely. This is what gets
    injected into the agent's prompt so it 'remembers' relevant knowledge.

    Args:
        results: Output from unified_search().
        max_chars: Hard cap on total output length.

    Returns:
        Formatted string ready for prompt injection, or "" if no results.
    """
    if not results:
        return ""

    lines = ["# Recalled Context (auto-retrieved from your memory layers)\n"]

    # Group by source
    by_source: dict[str, list] = {}
    for r in results:
        src = r.get("source", "unknown")
        by_source.setdefault(src, []).append(r)

    source_labels = {
        "session": "Past Conversations",
        "learning": "Absorbed Knowledge",
        "instinct": "Observed Patterns",
        "memory": "Agent Notes",
        "user_profile": "User Profile",
        "active_session": "Current Session",
        "semantic:session": "Related Conversations",
        "semantic:learning": "Related Knowledge",
        "semantic:instinct": "Related Patterns",
        "semantic:memory": "Related Notes",
        "semantic:user_profile": "Related Profile",
    }

    total = len(lines[0])
    for src, items in by_source.items():
        label = source_labels.get(src, src.title())
        header = f"\n## {label}"
        if total + len(header) > max_chars:
            break
        lines.append(header)
        total += len(header)

        for item in items:
            content = item.get("content", "")
            meta_parts = []
            if item.get("session_title"):
                meta_parts.append(f"session: {item['session_title']}")
            if item.get("session_date"):
                meta_parts.append(item["session_date"])
            if item.get("target"):
                meta_parts.append(f"from: {item['target']}")
            if item.get("verdict"):
                meta_parts.append(f"verdict: {item['verdict']}")
            if item.get("confidence"):
                meta_parts.append(f"conf: {item['confidence']:.1f}")
            if item.get("seen_count") and item["seen_count"] > 1:
                meta_parts.append(f"seen {item['seen_count']}x")

            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            entry = f"- {content}{meta}"

            if total + len(entry) + 1 > max_chars:
                lines.append("- ... [truncated for context window]")
                total = max_chars
                break
            lines.append(entry)
            total += len(entry) + 1

        if total >= max_chars:
            break

    return "\n".join(lines)


# ── Subscriptions ────────────────────────────────────────────


def add_subscription(user_id: str, platform: str, target_id: str,
                     target_name: str, target_type: str = "channel",
                     mode: str = "subscribe") -> bool:
    """Add a subscription (subscribe=digest, serve=active agent).
    Returns True if new, False if already exists."""
    conn = _connect()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO subscriptions
               (user_id, platform, target_id, target_name, target_type, mode, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, platform, target_id, target_name, target_type, mode,
             datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def remove_subscription(user_id: str, platform: str, target_id: str,
                        mode: str = "subscribe") -> bool:
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM subscriptions WHERE user_id=? AND platform=? AND target_id=? AND mode=?",
            (user_id, platform, target_id, mode)
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_subscriptions(user_id: str, mode: str = "subscribe",
                      platform: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if platform:
            rows = conn.execute(
                """SELECT * FROM subscriptions
                   WHERE user_id=? AND mode=? AND platform=?
                   ORDER BY platform, target_type, target_name""",
                (user_id, mode, platform)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM subscriptions
                   WHERE user_id=? AND mode=?
                   ORDER BY platform, target_type, target_name""",
                (user_id, mode)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_serve_targets(platform: str) -> list[dict]:
    """Get all targets in serve mode for a platform (used by adapters)."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT * FROM subscriptions
               WHERE platform=? AND mode='serve'""",
            (platform,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_subscribed(user_id: str, platform: str, target_id: str,
                  mode: str = "subscribe") -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT 1 FROM subscriptions
               WHERE user_id=? AND platform=? AND target_id=? AND mode=?""",
            (user_id, platform, target_id, mode)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ── Platform message storage (for digests) ──────────────────

def store_platform_message(platform: str, chat_id: str, user_id: str,
                           sender_name: str, content: str,
                           message_id: str | None = None,
                           timestamp: str | None = None):
    """Store an incoming message from a platform for digest purposes."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        # Deduplicate by message_id if provided
        if message_id:
            existing = conn.execute(
                "SELECT 1 FROM platform_messages WHERE platform=? AND message_id=? LIMIT 1",
                (platform, message_id)
            ).fetchone()
            if existing:
                return  # Already stored
        conn.execute(
            """INSERT INTO platform_messages
               (platform, chat_id, user_id, sender_name, content, timestamp, message_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (platform, chat_id, user_id, sender_name, content, ts, message_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_platform_messages(platform: str, chat_ids: list[str],
                          hours: int = 24) -> list[dict]:
    """Get messages from specific chats within the last N hours."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = _connect()
    try:
        placeholders = ",".join("?" * len(chat_ids))
        rows = conn.execute(
            f"""SELECT chat_id, user_id, sender_name, content, timestamp
                FROM platform_messages
                WHERE platform=? AND chat_id IN ({placeholders}) AND timestamp>=?
                ORDER BY timestamp ASC""",
            [platform] + chat_ids + [cutoff]
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cleanup_platform_messages(days: int = 7):
    """Delete platform messages older than N days."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _connect()
    try:
        conn.execute("DELETE FROM platform_messages WHERE timestamp < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()


# Initialize on import
init_db()
