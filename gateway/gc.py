"""Garbage collection agent — cleanup stale sessions, orphan skills, memory entropy.

Runs as /gc command or via cron. Reports what was cleaned and suggests
memory consolidation when needed.
"""
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("agenticEvolve.gc")

EXODIR = Path.home() / ".agenticEvolve"
DB_PATH = EXODIR / "memory" / "sessions.db"
MEMORY_PATH = EXODIR / "memory" / "MEMORY.md"
USER_PATH = EXODIR / "memory" / "USER.md"
QUEUE_DIR = EXODIR / "skills-queue"
COST_LOG = EXODIR / "logs" / "cost.log"
GATEWAY_LOG = EXODIR / "logs" / "gateway.log"

# Thresholds
STALE_SESSION_DAYS = 30       # Sessions older than this with ended_at set
EMPTY_SESSION_HOURS = 24      # Sessions with 0 messages older than this
ORPHAN_SKILL_DAYS = 7         # Queued skills older than this
COST_LOG_MAX_MB = 5           # Rotate cost.log if larger
GATEWAY_LOG_MAX_MB = 10       # Rotate gateway.log if larger
MEMORY_CHAR_LIMIT = 2200
USER_CHAR_LIMIT = 1375
MEMORY_ENTROPY_THRESHOLD = 0.85  # Warn if memory > 85% full


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def cleanup_stale_sessions(dry_run: bool = False) -> dict:
    """Remove ended sessions older than STALE_SESSION_DAYS and empty sessions older than EMPTY_SESSION_HOURS."""
    conn = _connect()
    now = datetime.now(timezone.utc)
    stale_cutoff = (now - timedelta(days=STALE_SESSION_DAYS)).isoformat()
    empty_cutoff = (now - timedelta(hours=EMPTY_SESSION_HOURS)).isoformat()

    # Find stale ended sessions
    stale = conn.execute(
        "SELECT id, source, started_at, message_count FROM sessions "
        "WHERE ended_at IS NOT NULL AND ended_at < ?",
        (stale_cutoff,)
    ).fetchall()

    # Find empty sessions (0 messages) older than threshold
    empty = conn.execute(
        "SELECT id, source, started_at FROM sessions "
        "WHERE message_count = 0 AND started_at < ?",
        (empty_cutoff,)
    ).fetchall()

    removed_stale = []
    removed_empty = []

    if not dry_run:
        for row in stale:
            sid = row["id"]
            # Delete messages first (FK), then FTS, then session
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            removed_stale.append({"id": sid, "source": row["source"], "messages": row["message_count"]})

        for row in empty:
            sid = row["id"]
            conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            removed_empty.append({"id": sid, "source": row["source"]})

        if removed_stale or removed_empty:
            conn.commit()
            # Optimize FTS index after bulk deletes (compacts fragmentation)
            try:
                conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('optimize')")
                conn.commit()
            except Exception as e:
                log.warning(f"FTS optimize failed: {e}")

    conn.close()

    return {
        "stale_removed": len(removed_stale) if not dry_run else len(stale),
        "empty_removed": len(removed_empty) if not dry_run else len(empty),
        "stale_details": [dict(r) for r in stale] if dry_run else removed_stale,
        "empty_details": [dict(r) for r in empty] if dry_run else removed_empty,
        "dry_run": dry_run,
    }


def cleanup_orphan_skills(dry_run: bool = False) -> dict:
    """Remove queued skills older than ORPHAN_SKILL_DAYS."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=ORPHAN_SKILL_DAYS)

    orphans = []
    for item in QUEUE_DIR.iterdir():
        if not item.is_dir():
            continue
        # Use directory mtime as creation proxy
        mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            orphans.append({
                "name": item.name,
                "age_days": (now - mtime).days,
                "path": str(item),
            })

    removed = []
    if not dry_run:
        for orphan in orphans:
            try:
                shutil.rmtree(orphan["path"])
                removed.append(orphan["name"])
                log.info(f"[gc] Removed orphan skill: {orphan['name']} ({orphan['age_days']}d old)")
            except Exception as e:
                log.warning(f"[gc] Failed to remove {orphan['name']}: {e}")

    return {
        "orphans_found": len(orphans),
        "orphans_removed": len(removed) if not dry_run else 0,
        "details": orphans,
        "dry_run": dry_run,
    }


def check_memory_entropy() -> dict:
    """Analyze MEMORY.md and USER.md for health: capacity, entry count, potential redundancy."""
    result = {"memory": {}, "user": {}}

    for label, path, limit in [("memory", MEMORY_PATH, MEMORY_CHAR_LIMIT),
                                ("user", USER_PATH, USER_CHAR_LIMIT)]:
        if not path.exists():
            result[label] = {"exists": False, "chars": 0, "limit": limit}
            continue

        content = path.read_text()
        chars = len(content)
        entries = [e.strip() for e in content.split("§") if e.strip()]
        usage_pct = chars / limit if limit > 0 else 0

        result[label] = {
            "exists": True,
            "chars": chars,
            "limit": limit,
            "usage_pct": round(usage_pct * 100, 1),
            "entry_count": len(entries),
            "near_full": usage_pct >= MEMORY_ENTROPY_THRESHOLD,
            "entries_preview": [e[:80] + "..." if len(e) > 80 else e for e in entries],
        }

    return result


def rotate_log(log_path: Path, max_mb: float) -> dict:
    """Rotate a log file if it exceeds max_mb."""
    if not log_path.exists():
        return {"rotated": False, "reason": "file not found"}

    size_mb = log_path.stat().st_size / (1024 * 1024)
    if size_mb < max_mb:
        return {"rotated": False, "size_mb": round(size_mb, 2), "max_mb": max_mb}

    # Rotate: rename current to .1, truncate
    rotated_path = log_path.with_suffix(log_path.suffix + ".1")
    if rotated_path.exists():
        rotated_path.unlink()  # Remove old rotation
    log_path.rename(rotated_path)
    log_path.touch()

    return {"rotated": True, "old_size_mb": round(size_mb, 2), "archived_to": str(rotated_path)}


def run_gc(dry_run: bool = False) -> dict:
    """Run full garbage collection cycle. Returns a report dict."""
    log.info(f"[gc] Starting garbage collection (dry_run={dry_run})")

    sessions = cleanup_stale_sessions(dry_run=dry_run)
    skills = cleanup_orphan_skills(dry_run=dry_run)
    memory = check_memory_entropy()

    logs_report = {}
    if not dry_run:
        logs_report["cost_log"] = rotate_log(COST_LOG, COST_LOG_MAX_MB)
        logs_report["gateway_log"] = rotate_log(GATEWAY_LOG, GATEWAY_LOG_MAX_MB)
    else:
        for label, path, max_mb in [("cost_log", COST_LOG, COST_LOG_MAX_MB),
                                     ("gateway_log", GATEWAY_LOG, GATEWAY_LOG_MAX_MB)]:
            if path.exists():
                size_mb = path.stat().st_size / (1024 * 1024)
                logs_report[label] = {"size_mb": round(size_mb, 2), "max_mb": max_mb,
                                       "would_rotate": size_mb >= max_mb}
            else:
                logs_report[label] = {"exists": False}

    # DB stats after cleanup
    conn = _connect()
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    conn.close()

    report = {
        "sessions": sessions,
        "skills": skills,
        "memory": memory,
        "logs": logs_report,
        "db_after": {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "db_size_mb": round(db_size / 1024 / 1024, 2),
        },
        "dry_run": dry_run,
    }

    log.info(f"[gc] Complete. Sessions removed: {sessions['stale_removed'] + sessions['empty_removed']}, "
             f"Orphan skills: {skills['orphans_found']}, "
             f"Memory: {memory['memory'].get('usage_pct', 0)}%/{memory['user'].get('usage_pct', 0)}%")

    return report


def format_gc_report(report: dict) -> str:
    """Format GC report as a Telegram-friendly message."""
    lines = []
    dry = " (DRY RUN)" if report.get("dry_run") else ""
    lines.append(f"*GC Report{dry}*\n")

    # Sessions
    s = report["sessions"]
    lines.append("*Sessions*")
    lines.append(f"  Stale removed: {s['stale_removed']}")
    lines.append(f"  Empty removed: {s['empty_removed']}")

    # Skills queue
    sk = report["skills"]
    lines.append(f"\n*Skills Queue*")
    lines.append(f"  Orphans found: {sk['orphans_found']}")
    if sk["orphans_found"] > 0:
        for d in sk["details"]:
            lines.append(f"  - {d['name']} ({d['age_days']}d old)")

    # Memory
    m = report["memory"]
    for label in ["memory", "user"]:
        info = m[label]
        if info.get("exists"):
            status = "NEAR FULL" if info.get("near_full") else "OK"
            lines.append(f"\n*{label.upper()}.md* [{status}]")
            lines.append(f"  {info['chars']}/{info['limit']} chars ({info['usage_pct']}%)")
            lines.append(f"  {info['entry_count']} entries")
        else:
            lines.append(f"\n*{label.upper()}.md* — not found")

    # Logs
    lg = report.get("logs", {})
    if lg:
        lines.append(f"\n*Logs*")
        for name, info in lg.items():
            if info.get("rotated"):
                lines.append(f"  {name}: rotated ({info['old_size_mb']}MB)")
            elif info.get("would_rotate"):
                lines.append(f"  {name}: {info['size_mb']}MB (would rotate at {info['max_mb']}MB)")
            elif "size_mb" in info:
                lines.append(f"  {name}: {info['size_mb']}MB")

    # DB
    db = report["db_after"]
    lines.append(f"\n*DB*: {db['total_sessions']} sessions, {db['total_messages']} messages, {db['db_size_mb']}MB")

    return "\n".join(lines)
