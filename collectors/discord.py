#!/usr/bin/env python3
"""
Discord signal collector for the /evolve pipeline.

Reads messages from the Discord desktop app's Chromium disk cache.
Zero network calls — only reads local files that Discord already cached.

This is the Discord equivalent of collectors/wechat.py. The WeChat collector
reads decrypted SQLCipher DBs; this one reads Chromium HTTP cache responses
from ~/Library/Application Support/discord/Cache/Cache_Data/.

Signal format matches other collectors:
  {id, source, timestamp, author, title, content, url, metadata}

Usage:
    python3 discord.py                # writes to $SIGNALS_DIR/<today>/discord.json
    python3 discord.py --hours 48     # last 48 hours instead of 24
    python3 discord.py --channel 123  # specific channel only
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import the cache reader
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "discord-local"))
from read_cache import read_cached_messages

SIGNALS_DIR = Path(
    os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals"))
)

DEFAULT_HOURS = 24
MAX_MSGS_PER_CHANNEL = 200
MAX_CONTENT_LEN = 8000


def collect_discord_signals(
    hours: int = DEFAULT_HOURS,
    channel_id: str | None = None,
) -> list[dict]:
    """
    Collect Discord messages from Chromium cache as evolve signals.

    Groups messages by channel_id. Returns one signal per active channel.
    """
    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # Go back `hours` from now
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    messages = read_cached_messages(channel_id=channel_id, since=since)

    # Group by channel
    by_channel: dict[str, list[dict]] = {}
    for msg in messages:
        ch = msg.get("channel_id", "unknown")
        by_channel.setdefault(ch, []).append(msg)

    signals = []
    for ch_id, ch_msgs in by_channel.items():
        # Limit per channel
        ch_msgs = ch_msgs[:MAX_MSGS_PER_CHANNEL]

        # Build condensed content
        content_lines = []
        total_len = 0
        senders = set()

        for msg in ch_msgs:
            author = msg.get("author", {})
            name = author.get("global_name") or author.get("username", "?")
            senders.add(name)
            ts_str = msg.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                time_str = ts.strftime("%H:%M")
            except (ValueError, TypeError):
                time_str = "?"

            text = msg.get("content", "")
            # Include attachment info
            attachments = msg.get("attachments", [])
            if attachments:
                att_info = ", ".join(
                    a.get("filename", "file") for a in attachments
                )
                text += f" [attachments: {att_info}]"

            # Include embed titles
            embeds = msg.get("embeds", [])
            for e in embeds:
                title = e.get("title", "")
                if title:
                    text += f" [embed: {title}]"

            line = f"[{time_str}] {name}: {text}"
            if total_len + len(line) > MAX_CONTENT_LEN:
                content_lines.append(
                    f"... ({len(ch_msgs) - len(content_lines)} more messages)"
                )
                break
            content_lines.append(line)
            total_len += len(line)

        if not content_lines:
            continue

        # Timestamps
        first_ts = ch_msgs[0].get("timestamp", "")
        last_ts = ch_msgs[-1].get("timestamp", "")

        # Try to get a guild_id from the messages (not always present)
        guild_id = ""
        for msg in ch_msgs[:5]:
            if msg.get("guild_id"):
                guild_id = msg["guild_id"]
                break

        signal = {
            "id": f"discord-{ch_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "source": "discord",
            "timestamp": last_ts,
            "author": f"Channel {ch_id}",
            "title": f"Discord #{ch_id} ({len(ch_msgs)} messages, last {hours}h)",
            "content": "\n".join(content_lines),
            "url": f"https://discord.com/channels/{guild_id}/{ch_id}"
            if guild_id
            else "",
            "metadata": {
                "channel_id": ch_id,
                "guild_id": guild_id,
                "message_count": len(ch_msgs),
                "unique_senders": len(senders),
                "first_message": first_ts[:19] if first_ts else "",
                "last_message": last_ts[:19] if last_ts else "",
                "points": len(ch_msgs),  # engagement proxy for ranking
            },
        }
        signals.append(signal)

    return signals


def get_cached_channel_ids() -> list[str]:
    """Return list of channel IDs that have cached messages.

    Fast scan — only reads file headers, no decompression.
    Used by _discover_targets() for the /subscribe modal to show
    available Discord channels without making API calls.
    """
    import importlib
    _cache_dir = str(Path(__file__).resolve().parent.parent / "tools" / "discord-local")
    if _cache_dir not in sys.path:
        sys.path.insert(0, _cache_dir)
    _rc = importlib.import_module("read_cache")
    return _rc.get_cached_channel_ids()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Discord signal collector (reads Chromium cache)"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        help="Hours of history to collect (default: 24)",
    )
    parser.add_argument("--channel", help="Filter to a specific channel ID")
    args = parser.parse_args()

    signals = collect_discord_signals(hours=args.hours, channel_id=args.channel)

    if not signals:
        print(
            f"No Discord messages in the last {args.hours} hours (from cache)",
            file=sys.stderr,
        )

    # Write to signals dir
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "discord.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(signals)} channel signals to {outfile}", file=sys.stderr)
    for s in signals:
        meta = s["metadata"]
        print(
            f"  #{meta['channel_id']}: {meta['message_count']} msgs, "
            f"{meta['unique_senders']} senders",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
