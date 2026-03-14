#!/usr/bin/env python3
"""
WeChat signal collector for the /evolve pipeline.

Reads decrypted WeChat group chat databases and extracts the last 24 hours
of tech-related discussions as signals for the ANALYZE stage.

Signal format matches github.sh / hackernews.sh:
  {id, source, timestamp, author, title, content, url, metadata}

Usage:
    python3 wechat.py              # writes to $SIGNALS_DIR/<today>/wechat-groups.json
    python3 wechat.py --hours 48   # last 48 hours instead of 24

Requires: decrypted DBs at ~/.agenticEvolve/tools/wechat-decrypt/decrypted/
  Run `sudo ./find_keys && python3 decrypt_db.py` first if DBs are stale.
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS_DIR = Path.home() / ".agenticEvolve" / "tools" / "wechat-decrypt"
DECRYPTED_DIR = TOOLS_DIR / "decrypted"
SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))

# Only collect from group chats (chatrooms)
# Messages older than this many hours are ignored
DEFAULT_HOURS = 24

# Max messages per group to include (avoid huge payloads)
MAX_MSGS_PER_GROUP = 200

# Max total content length per signal (chars)
MAX_CONTENT_LEN = 8000


def load_contacts(decrypted_dir: Path) -> dict:
    """Load contact name mapping."""
    contact_db = decrypted_dir / "contact" / "contact.db"
    if not contact_db.exists():
        return {}
    contacts = {}
    try:
        conn = sqlite3.connect(str(contact_db))
        for row in conn.execute("SELECT username, nick_name, remark FROM contact"):
            wxid, nick, remark = row
            if wxid:
                contacts[wxid] = remark if remark else (nick or wxid)
        conn.close()
    except Exception:
        pass
    return contacts


def get_conversation_map(conn) -> dict:
    """Build mapping: username -> Msg_<md5(username)> table name."""
    mapping = {}
    try:
        names = [r[0] for r in conn.execute("SELECT user_name FROM Name2Id").fetchall()]
        tables = set(
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
            ).fetchall()
            if "_SENDERID" not in r[0] and "_SERVERID" not in r[0]
            and "_SORTSEQ" not in r[0] and "_TYPE_SEQ" not in r[0]
        )
        for name in names:
            if not name:
                continue
            h = hashlib.md5(name.encode()).hexdigest()
            tname = f"Msg_{h}"
            if tname in tables:
                mapping[name] = tname
    except sqlite3.OperationalError:
        pass
    return mapping


def extract_group_messages(decrypted_dir: Path, hours: int) -> list[dict]:
    """Extract recent group chat messages from decrypted DBs.

    Returns list of signal dicts, one per group with activity.
    """
    contacts = load_contacts(decrypted_dir)
    cutoff = int(time.time()) - (hours * 3600)

    signals = []
    message_dbs = sorted((decrypted_dir / "message").glob("message_*.db"))

    for db_path in message_dbs:
        try:
            conn = sqlite3.connect(str(db_path))
            conv_map = get_conversation_map(conn)
        except Exception:
            continue

        for username, table_name in conv_map.items():
            # Only group chats
            if "@chatroom" not in username:
                continue

            try:
                rows = conn.execute(
                    f"SELECT local_type, create_time, message_content "
                    f"FROM [{table_name}] "
                    f"WHERE create_time >= ? AND local_type = 1 "
                    f"ORDER BY create_time ASC "
                    f"LIMIT ?",
                    (cutoff, MAX_MSGS_PER_GROUP)
                ).fetchall()
            except sqlite3.OperationalError:
                continue

            if not rows:
                continue

            # Parse messages
            messages = []
            for msg_type, ts, content in rows:
                if not content or not isinstance(content, str):
                    continue

                # Group messages: "sender_wxid:\ncontent"
                sender = username
                text = content
                if ":\n" in content:
                    s, _, t = content.partition(":\n")
                    if s and len(s) < 100 and "\n" not in s:
                        sender = s
                        text = t

                sender_name = contacts.get(sender, sender)
                messages.append({
                    "sender": sender_name,
                    "text": text.strip(),
                    "time": datetime.fromtimestamp(ts).strftime("%H:%M"),
                })

            if not messages:
                continue

            # Build content: condensed conversation
            content_lines = []
            total_len = 0
            for m in messages:
                line = f"[{m['time']}] {m['sender']}: {m['text']}"
                if total_len + len(line) > MAX_CONTENT_LEN:
                    content_lines.append(f"... ({len(messages) - len(content_lines)} more messages)")
                    break
                content_lines.append(line)
                total_len += len(line)

            group_name = contacts.get(username, username)
            first_ts = rows[0][1]
            last_ts = rows[-1][1]

            signal = {
                "id": f"wechat-group-{username}-{datetime.now().strftime('%Y%m%d')}",
                "source": "wechat",
                "timestamp": datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat(),
                "author": group_name,
                "title": f"WeChat group: {group_name} ({len(messages)} messages, last {hours}h)",
                "content": "\n".join(content_lines),
                "url": "",
                "metadata": {
                    "group_id": username,
                    "group_name": group_name,
                    "message_count": len(messages),
                    "unique_senders": len(set(m["sender"] for m in messages)),
                    "first_message": datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d %H:%M"),
                    "last_message": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M"),
                    "points": len(messages),  # engagement proxy for ranking
                },
            }
            signals.append(signal)

        conn.close()

    return signals


def check_db_freshness(decrypted_dir: Path, max_age_hours: int = 2) -> bool:
    """Check if decrypted DBs are fresh enough (modified within max_age_hours)."""
    msg_db = decrypted_dir / "message" / "message_0.db"
    if not msg_db.exists():
        return False
    age = time.time() - msg_db.stat().st_mtime
    return age < max_age_hours * 3600


def re_decrypt(tools_dir: Path) -> bool:
    """Re-run decrypt_db.py to refresh decrypted databases.

    Note: This does NOT re-extract keys. Keys are extracted via sudo find_keys
    which requires root. We assume wechat_keys.json is already present and
    up-to-date (keys don't change until WeChat restarts).
    """
    import subprocess

    keys_file = tools_dir / "wechat_keys.json"
    if not keys_file.exists():
        print("No wechat_keys.json found — run `sudo ./find_keys` first", file=sys.stderr)
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(tools_dir / "decrypt_db.py"),
             "--keys", str(keys_file),
             "--output", str(tools_dir / "decrypted")],
            capture_output=True, text=True, timeout=120,
            cwd=str(tools_dir),
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Re-decrypt failed: {e}", file=sys.stderr)
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="WeChat group chat signal collector")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS,
                        help="Hours of history to collect (default: 24)")
    parser.add_argument("--no-refresh", action="store_true",
                        help="Don't re-decrypt DBs even if stale")
    args = parser.parse_args()

    # Check if decrypted DBs exist
    if not DECRYPTED_DIR.exists() or not (DECRYPTED_DIR / "message").exists():
        print("No decrypted DBs found. Run the decrypt pipeline first.", file=sys.stderr)
        print("  cd ~/.agenticEvolve/tools/wechat-decrypt", file=sys.stderr)
        print("  sudo ./find_keys && python3 decrypt_db.py", file=sys.stderr)
        sys.exit(1)

    # Re-decrypt if DBs are stale (older than 2 hours)
    if not args.no_refresh and not check_db_freshness(DECRYPTED_DIR, max_age_hours=2):
        print("Decrypted DBs are stale, refreshing...", file=sys.stderr)
        if re_decrypt(TOOLS_DIR):
            print("Re-decrypted successfully", file=sys.stderr)
        else:
            print("Re-decrypt failed, using stale data", file=sys.stderr)

    # Extract signals
    signals = extract_group_messages(DECRYPTED_DIR, hours=args.hours)

    if not signals:
        print("No group chat messages in the last {} hours".format(args.hours), file=sys.stderr)
        # Write empty array so the pipeline doesn't error
        signals = []

    # Write to signals dir
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "wechat-groups.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(signals)} group signals to {outfile}", file=sys.stderr)
    for s in signals:
        meta = s["metadata"]
        print(f"  {meta['group_name']}: {meta['message_count']} msgs, "
              f"{meta['unique_senders']} senders", file=sys.stderr)


if __name__ == "__main__":
    main()
