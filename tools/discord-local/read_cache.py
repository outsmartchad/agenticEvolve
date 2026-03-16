#!/usr/bin/env python3
"""
Read Discord messages from Chrome/Electron disk cache.

Discord's Electron app caches API responses in Chromium's disk cache at:
  ~/Library/Application Support/discord/Cache/Cache_Data/

Each cache file has:
  [0:101]  Chromium cache metadata (varies)
  [101:N]  gzip-compressed response body
  [N:]     HTTP response headers

This module extracts messages from /api/v9/channels/{id}/messages responses,
as well as guild search results from /api/v9/guilds/{id}/messages/search.

Usage:
    python3 read_cache.py                          # dump all cached messages as JSON
    python3 read_cache.py --channel 1234567890     # filter by channel ID
    python3 read_cache.py --since 2026-03-01       # filter by date
    python3 read_cache.py --stats                  # show cache statistics
"""

import json
import os
import re
import sys
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CACHE_DIR = Path.home() / "Library/Application Support/discord/Cache/Cache_Data"

# Chromium cache metadata offset — body starts after this
# This can vary slightly; we try multiple offsets if the first fails
METADATA_OFFSETS = [101, 97, 105, 109, 0]


def _decompress_body(data: bytes, http_offset: int) -> Optional[bytes]:
    """Try to decompress the response body from cache file data."""
    body_section = data[:http_offset]

    for offset in METADATA_OFFSETS:
        if offset >= len(body_section):
            continue
        chunk = body_section[offset:]
        # Try gzip (zlib with auto-detect)
        try:
            return zlib.decompress(chunk, 15 + 32)
        except Exception:
            pass
        # Try raw deflate
        try:
            return zlib.decompress(chunk, -15)
        except Exception:
            pass

    # Maybe it's uncompressed JSON
    for offset in METADATA_OFFSETS:
        if offset >= len(body_section):
            continue
        chunk = body_section[offset:]
        try:
            json.loads(chunk)
            return chunk
        except Exception:
            pass

    return None


def _parse_cache_file(filepath: str) -> Optional[dict]:
    """
    Parse a single Chromium cache file.

    Returns dict with keys:
      - url: the request URL
      - status: HTTP status code
      - content_type: response content-type
      - body: parsed JSON body (list or dict), or None
      - timestamp: file modification time
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except (OSError, PermissionError):
        return None

    if len(data) < 200:
        return None

    # Find HTTP response header (at end of file)
    http_idx = data.find(b"HTTP/")
    if http_idx == -1:
        return None

    # Extract URL from the start of the file
    # Format: "1/0/https://discord.com/api/v9/..."
    text_start = data[:min(4096, http_idx)].decode("utf-8", errors="replace")
    url_match = re.search(
        r"https://discord(?:app)?\.com/api/v\d+/\S+", text_start
    )
    if not url_match:
        return None

    url = url_match.group(0)

    # Parse HTTP status
    header_text = data[http_idx : http_idx + 2000].decode("utf-8", errors="replace")
    status_match = re.match(r"HTTP/[\d.]+ (\d+)", header_text)
    status = int(status_match.group(1)) if status_match else 0

    # Only process 200 OK responses
    if status != 200:
        return None

    # Check content type
    ct_match = re.search(r"content-type:\s*(\S+)", header_text, re.IGNORECASE)
    content_type = ct_match.group(1) if ct_match else ""

    if "json" not in content_type:
        return None

    # Decompress body
    raw_body = _decompress_body(data, http_idx)
    if raw_body is None:
        return None

    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    return {
        "url": url,
        "status": status,
        "content_type": content_type,
        "body": body,
        "timestamp": os.path.getmtime(filepath),
    }


def read_cached_messages(
    channel_id: Optional[str] = None,
    since: Optional[datetime] = None,
    cache_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Read all cached Discord messages.

    Args:
        channel_id: filter to a specific channel
        since: only return messages after this datetime
        cache_dir: override cache directory path

    Returns:
        List of message dicts (Discord API format), deduplicated by message ID,
        sorted by timestamp ascending.
    """
    cache_dir = cache_dir or CACHE_DIR
    if not cache_dir.exists():
        return []

    seen_ids: set[str] = set()
    messages: list[dict] = []

    for filename in os.listdir(cache_dir):
        filepath = os.path.join(cache_dir, filename)
        if not os.path.isfile(filepath):
            continue

        # Quick pre-filter: check if file contains /messages
        try:
            with open(filepath, "rb") as f:
                header = f.read(4096)
        except (OSError, PermissionError):
            continue

        if b"/messages" not in header:
            continue

        # If filtering by channel, check the URL
        if channel_id:
            if f"/channels/{channel_id}/messages".encode() not in header:
                # Also check guild search results
                if b"/messages/search" not in header:
                    continue

        parsed = _parse_cache_file(filepath)
        if parsed is None:
            continue

        body = parsed["body"]

        # Handle different response formats
        msg_list: list[dict] = []

        if isinstance(body, list):
            # Direct /channels/{id}/messages response
            msg_list = body
        elif isinstance(body, dict):
            # Guild search: {"messages": [[msg, ...], ...], "total_results": N}
            if "messages" in body and isinstance(body["messages"], list):
                for group in body["messages"]:
                    if isinstance(group, list):
                        msg_list.extend(group)
            # Single message response
            elif "id" in body and "content" in body:
                msg_list = [body]

        for msg in msg_list:
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id")
            if not msg_id or msg_id in seen_ids:
                continue

            # Channel filter
            if channel_id and msg.get("channel_id") != channel_id:
                continue

            # Date filter
            if since:
                ts_str = msg.get("timestamp", "")
                try:
                    msg_dt = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00")
                    )
                    if msg_dt < since:
                        continue
                except (ValueError, TypeError):
                    pass

            seen_ids.add(msg_id)
            messages.append(msg)

    # Sort by timestamp
    messages.sort(key=lambda m: m.get("timestamp", ""))
    return messages


def get_cached_channel_ids(cache_dir: Optional[Path] = None) -> list[str]:
    """Fast scan: return channel IDs that have cached messages.

    Only reads file headers (first 4KB) — does NOT decompress bodies.
    Sorted by number of cache files per channel (most active first).
    """
    cache_dir = cache_dir or CACHE_DIR
    if not cache_dir.exists():
        return []

    channels: dict[str, int] = {}
    for filename in os.listdir(cache_dir):
        filepath = os.path.join(cache_dir, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, "rb") as f:
                header = f.read(4096)
        except (OSError, PermissionError):
            continue
        text = header.decode("utf-8", errors="replace")
        m = re.search(r"/channels/(\d+)/messages", text)
        if m:
            channels[m.group(1)] = channels.get(m.group(1), 0) + 1
    return sorted(channels.keys(), key=lambda c: -channels[c])


def get_cache_stats(cache_dir: Optional[Path] = None) -> dict:
    """
    Get statistics about the Discord cache.

    Returns dict with:
      - total_files: number of cache files
      - api_files: files with Discord API URLs
      - message_files: files with /messages endpoints
      - unique_channels: set of channel IDs with cached messages
      - total_messages: deduplicated message count
      - endpoint_counts: Counter of API endpoint categories
      - oldest_message: oldest message timestamp
      - newest_message: newest message timestamp
    """
    cache_dir = cache_dir or CACHE_DIR
    if not cache_dir.exists():
        return {"error": "Cache directory not found"}

    stats = {
        "total_files": 0,
        "api_files": 0,
        "message_files": 0,
        "channels": defaultdict(int),
        "endpoints": defaultdict(int),
    }

    for filename in os.listdir(cache_dir):
        filepath = os.path.join(cache_dir, filename)
        if not os.path.isfile(filepath):
            continue
        stats["total_files"] += 1

        try:
            with open(filepath, "rb") as f:
                header = f.read(4096)
        except (OSError, PermissionError):
            continue

        text = header.decode("utf-8", errors="replace")
        m = re.search(r"https://discord(?:app)?\.com/api/v\d+/(\w+)", text)
        if m:
            stats["api_files"] += 1
            stats["endpoints"][m.group(1)] += 1

        ch_match = re.search(r"/channels/(\d+)/messages", text)
        if ch_match:
            stats["message_files"] += 1
            stats["channels"][ch_match.group(1)] += 1

    # Get message count and date range
    all_messages = read_cached_messages(cache_dir=cache_dir)
    timestamps = []
    for msg in all_messages:
        ts = msg.get("timestamp", "")
        try:
            timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        except (ValueError, TypeError):
            pass

    return {
        "total_files": stats["total_files"],
        "api_files": stats["api_files"],
        "message_files": stats["message_files"],
        "unique_channels": len(stats["channels"]),
        "total_messages": len(all_messages),
        "oldest_message": min(timestamps).isoformat() if timestamps else None,
        "newest_message": max(timestamps).isoformat() if timestamps else None,
        "top_channels": sorted(
            stats["channels"].items(), key=lambda x: -x[1]
        )[:20],
        "endpoint_counts": dict(
            sorted(stats["endpoints"].items(), key=lambda x: -x[1])
        ),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Read Discord messages from Chromium disk cache"
    )
    parser.add_argument("--channel", help="Filter by channel ID")
    parser.add_argument("--since", help="Filter messages after date (YYYY-MM-DD)")
    parser.add_argument(
        "--stats", action="store_true", help="Show cache statistics"
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format",
    )
    parser.add_argument("--limit", type=int, help="Limit number of messages")
    args = parser.parse_args()

    if args.stats:
        stats = get_cache_stats()
        print(json.dumps(stats, indent=2, default=str))
        return

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).replace(
            tzinfo=timezone.utc
        )

    messages = read_cached_messages(channel_id=args.channel, since=since)

    if args.limit:
        messages = messages[: args.limit]

    if args.format == "json":
        print(json.dumps(messages, indent=2, ensure_ascii=False))
    else:
        for msg in messages:
            author = msg.get("author", {})
            name = author.get("global_name") or author.get("username", "?")
            ts = msg.get("timestamp", "?")[:19]
            content = msg.get("content", "")
            ch = msg.get("channel_id", "?")
            print(f"[{ts}] #{ch} {name}: {content[:200]}")

    print(f"\n--- {len(messages)} messages ---", file=sys.stderr)


if __name__ == "__main__":
    main()
