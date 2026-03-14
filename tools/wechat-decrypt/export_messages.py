#!/usr/bin/env python3
"""
export_messages.py — Read and export decrypted WeChat messages (macOS WeChat 4.x).

Usage:
    python3 export_messages.py                               # list all conversations
    python3 export_messages.py --contact "hichenyuxuan"      # export specific contact
    python3 export_messages.py --group "xxx@chatroom"        # export specific group
    python3 export_messages.py --search "keyword"            # search all messages
    python3 export_messages.py --recent 100                  # last 100 messages across all chats
    python3 export_messages.py --format json                 # output as JSON (default: text)
    python3 export_messages.py --format csv                  # output as CSV
    python3 export_messages.py --all                         # export ALL messages
"""

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MSG_TYPES = {
    1: "text",
    3: "image",
    34: "voice",
    42: "contact_card",
    43: "video",
    47: "emoji",
    49: "link/file/miniapp",
    10000: "system",
    10002: "revoked",
}


def load_contacts(decrypted_dir):
    """Load contact name mapping from decrypted contact.db."""
    contact_db = Path(decrypted_dir) / "contact" / "contact.db"
    if not contact_db.exists():
        return {}

    contacts = {}
    try:
        conn = sqlite3.connect(str(contact_db))
        cursor = conn.cursor()
        cursor.execute("SELECT username, nick_name, remark FROM contact")
        for row in cursor.fetchall():
            wxid, nick, remark = row
            if wxid:
                contacts[wxid] = remark if remark else (nick or wxid)
        conn.close()
    except Exception as e:
        print(f"  [-] Error loading contacts: {e}", file=sys.stderr)
    return contacts


def get_conversation_map(conn):
    """Build mapping: username -> Msg_<md5(username)> table name.
    Uses Name2Id table + verifies table exists."""
    mapping = {}  # username -> table_name
    try:
        cursor = conn.cursor()
        names = [r[0] for r in cursor.execute("SELECT user_name FROM Name2Id").fetchall()]
        tables = set(
            r[0] for r in cursor.execute(
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


def parse_group_message(content, is_group):
    """Parse group message content. Group messages have format 'sender_wxid:\\ncontent'.
    Returns (sender_wxid, actual_content)."""
    if not content:
        return None, ""
    # Handle bytes (WCDB compressed content may be returned as bytes)
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8", errors="replace")
        except Exception:
            return None, repr(content)
    if is_group and ":\n" in content:
        sender, _, text = content.partition(":\n")
        # Verify sender looks like a wxid (not a false split)
        if sender and len(sender) < 100 and "\n" not in sender:
            return sender, text
    return None, content


def query_conversation(conn, table_name, username, search=None, limit=None):
    """Query messages from a single conversation table."""
    messages = []
    is_group = "@chatroom" in username
    cursor = conn.cursor()

    conditions = []
    params = []

    if search:
        conditions.append("message_content LIKE ?")
        params.append(f"%{search}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order = "ORDER BY create_time DESC" if limit else "ORDER BY create_time ASC"
    limit_clause = f"LIMIT {limit}" if limit else ""

    sql = (f"SELECT local_id, local_type, create_time, message_content, "
           f"source, real_sender_id "
           f"FROM [{table_name}] {where} {order} {limit_clause}")

    try:
        cursor.execute(sql, params)
    except sqlite3.OperationalError:
        return messages

    for row in cursor.fetchall():
        local_id, msg_type, create_time, content, source, sender_id = row

        # Parse sender from group message content
        actual_sender, actual_content = parse_group_message(content, is_group)

        # Determine if sent by self
        # In group chats: if no sender prefix, it's from self
        # In 1:1 chats: real_sender_id == 0 means from self (heuristic)
        if is_group:
            is_sender = actual_sender is None and msg_type != 10000
        else:
            is_sender = sender_id == 0 if sender_id is not None else False

        msg = {
            "id": local_id,
            "conversation": username,
            "sender": actual_sender or ("self" if is_sender else username),
            "is_sender": is_sender,
            "type": MSG_TYPES.get(msg_type, f"unknown({msg_type})"),
            "type_id": msg_type,
            "content": actual_content or "",
            "timestamp": create_time or 0,
            "time": datetime.fromtimestamp(create_time).strftime(
                "%Y-%m-%d %H:%M:%S") if create_time else "",
        }
        messages.append(msg)

    return messages


def find_message_dbs(decrypted_dir):
    """Find all decrypted message_*.db files."""
    p = Path(decrypted_dir) / "message"
    if not p.exists():
        p = Path(decrypted_dir)
    return sorted(p.glob("message_*.db"))


def list_conversations(decrypted_dir, contacts):
    """List all conversations with message counts."""
    db_files = find_message_dbs(decrypted_dir)
    all_convos = {}

    for db_path in db_files:
        conn = sqlite3.connect(str(db_path))
        conv_map = get_conversation_map(conn)

        for username, table_name in conv_map.items():
            try:
                cursor = conn.cursor()
                row = cursor.execute(
                    f"SELECT COUNT(*), MIN(create_time), MAX(create_time) "
                    f"FROM [{table_name}]"
                ).fetchone()
                if row and row[0] > 0:
                    all_convos[username] = {
                        "count": row[0],
                        "first": row[1] or 0,
                        "last": row[2] or 0,
                        "db": db_path.name,
                    }
            except sqlite3.OperationalError:
                continue
        conn.close()

    # Sort by last message time (descending)
    sorted_convos = sorted(all_convos.items(),
                           key=lambda x: x[1]["last"], reverse=True)

    print(f"\n{'Contact/Group':<42} {'Name':<20} {'Msgs':>6} {'Last Message'}")
    print("-" * 90)
    for username, info in sorted_convos:
        name = contacts.get(username, "")
        last = datetime.fromtimestamp(info["last"]).strftime(
            "%Y-%m-%d %H:%M") if info["last"] else ""
        is_group = "@chatroom" in username
        prefix = "[G] " if is_group else "    "
        print(f"{prefix}{username:<38} {name:<20} {info['count']:>6} {last}")

    print(f"\nTotal: {len(sorted_convos)} conversations, "
          f"{sum(c['count'] for c in all_convos.values())} messages")


def query_all_messages(decrypted_dir, contact=None, group=None,
                       search=None, limit=None, export_all=False):
    """Query messages across all message DBs."""
    db_files = find_message_dbs(decrypted_dir)
    all_messages = []

    for db_path in db_files:
        conn = sqlite3.connect(str(db_path))
        conv_map = get_conversation_map(conn)

        for username, table_name in conv_map.items():
            # Filter by contact/group
            if contact and username != contact:
                continue
            if group and username != group:
                continue
            if not export_all and not contact and not group and not search and not limit:
                continue  # require at least one filter or --all

            msgs = query_conversation(conn, table_name, username,
                                      search=search, limit=limit)
            all_messages.extend(msgs)

        conn.close()

    if limit and not contact and not group:
        # Global limit: sort by time desc and take top N
        all_messages.sort(key=lambda m: m["timestamp"], reverse=True)
        all_messages = all_messages[:limit]

    return all_messages


def format_text(messages, contacts):
    """Format messages as readable text."""
    lines = []
    current_conv = None
    sorted_msgs = sorted(messages, key=lambda m: (m["conversation"], m["timestamp"]))

    for msg in sorted_msgs:
        if msg["conversation"] != current_conv:
            current_conv = msg["conversation"]
            conv_name = contacts.get(current_conv, current_conv)
            lines.append(f"\n{'='*60}")
            lines.append(f"  Conversation: {conv_name} ({current_conv})")
            lines.append(f"{'='*60}\n")

        sender = "You" if msg["is_sender"] else contacts.get(
            msg["sender"], msg["sender"])
        content = msg["content"]
        if msg["type"] != "text" and msg["type_id"] != 10000:
            content = f"[{msg['type']}] {content[:200]}"

        lines.append(f"[{msg['time']}] {sender}: {content}")

    return "\n".join(lines)


def format_json(messages, contacts):
    """Format messages as JSON."""
    for msg in messages:
        msg["sender_name"] = "You" if msg["is_sender"] else contacts.get(
            msg["sender"], msg["sender"])
        msg["conversation_name"] = contacts.get(
            msg["conversation"], msg["conversation"])
    return json.dumps(
        sorted(messages, key=lambda m: m["timestamp"]),
        ensure_ascii=False, indent=2)


def format_csv(messages, contacts):
    """Format messages as CSV."""
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time", "conversation", "sender", "type", "content"])
    for msg in sorted(messages, key=lambda m: m["timestamp"]):
        sender = "You" if msg["is_sender"] else contacts.get(
            msg["sender"], msg["sender"])
        conv_name = contacts.get(msg["conversation"], msg["conversation"])
        writer.writerow([msg["time"], conv_name, sender,
                         msg["type"], msg["content"][:500]])
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(
        description="Export decrypted WeChat messages (macOS)")
    parser.add_argument("--dir", default="./decrypted",
                        help="Decrypted DB directory")
    parser.add_argument("--contact", help="Filter by contact wxid or username")
    parser.add_argument("--group", help="Filter by group (xxx@chatroom)")
    parser.add_argument("--search", help="Search messages by keyword")
    parser.add_argument("--recent", type=int,
                        help="Show N most recent messages")
    parser.add_argument("--list", action="store_true",
                        help="List all conversations")
    parser.add_argument("--all", action="store_true",
                        help="Export ALL messages")
    parser.add_argument("--format", choices=["text", "json", "csv"],
                        default="text")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    decrypted_dir = Path(args.dir)
    if not decrypted_dir.exists():
        print(f"[-] Directory not found: {decrypted_dir}", file=sys.stderr)
        print("    Run decrypt_db.py first.", file=sys.stderr)
        return 1

    contacts = load_contacts(decrypted_dir)
    print(f"[*] Loaded {len(contacts)} contacts", file=sys.stderr)

    # List conversations
    if args.list:
        list_conversations(decrypted_dir, contacts)
        return 0

    # Need at least one action
    if not args.contact and not args.group and not args.search \
       and not args.recent and not args.all:
        # Default to listing conversations
        list_conversations(decrypted_dir, contacts)
        return 0

    # Query messages
    messages = query_all_messages(
        decrypted_dir,
        contact=args.contact,
        group=args.group,
        search=args.search,
        limit=args.recent,
        export_all=args.all,
    )

    if not messages:
        print("[-] No messages found.", file=sys.stderr)
        return 1

    print(f"[*] Found {len(messages)} message(s)", file=sys.stderr)

    # Format
    if args.format == "json":
        output = format_json(messages, contacts)
    elif args.format == "csv":
        output = format_csv(messages, contacts)
    else:
        output = format_text(messages, contacts)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[+] Written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
