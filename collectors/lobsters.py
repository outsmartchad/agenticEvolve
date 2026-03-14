#!/usr/bin/env python3
"""Lobste.rs collector — curated tech news with high signal-to-noise ratio."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))


def fetch_lobsters() -> list[dict]:
    """Fetch hottest stories from Lobste.rs JSON API."""
    signals = []
    try:
        req = Request("https://lobste.rs/hottest.json", headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=15) as resp:
            stories = json.loads(resp.read().decode("utf-8"))

        for s in stories[:30]:
            score = s.get("score", 0)
            if score < 5:
                continue

            signals.append({
                "id": f"lobsters-{s.get('short_id', '')}",
                "source": "lobsters",
                "timestamp": s.get("created_at", ""),
                "author": s.get("submitter_user", {}).get("username", "") if isinstance(s.get("submitter_user"), dict) else "",
                "title": s.get("title", ""),
                "content": s.get("description", "") or s.get("title", ""),
                "url": s.get("url", "") or s.get("comments_url", ""),
                "metadata": {
                    "points": score,
                    "replies": s.get("comment_count", 0),
                    "tags": s.get("tags", []),
                    "relevance_tags": ["lobsters"] + s.get("tags", []),
                }
            })
    except Exception as e:
        print(f"Lobste.rs error: {e}", file=sys.stderr)

    return signals


def main():
    signals = fetch_lobsters()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "lobsters.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print(f"Lobste.rs: {len(signals)} signals → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
