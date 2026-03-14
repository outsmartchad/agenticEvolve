#!/usr/bin/env python3
"""Product Hunt collector — scrapes today's top launches via public RSS/web."""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))

CATEGORIES = [
    "https://www.producthunt.com/feed?category=developer-tools",
    "https://www.producthunt.com/feed?category=artificial-intelligence",
    "https://www.producthunt.com/feed",  # general (top)
]


def fetch_rss(url: str) -> list[dict]:
    """Fetch and parse Product Hunt RSS feed."""
    signals = []
    try:
        req = Request(url, headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")

        root = ET.fromstring(data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Try Atom format first, then RSS
        entries = root.findall("atom:entry", ns) or root.findall(".//item")

        for item in entries:
            title = item.findtext("atom:title", "", ns) or item.findtext("title", "")
            link_el = item.find("atom:link", ns)
            link = (link_el.get("href", "") if link_el is not None else "") or item.findtext("link", "")
            desc = item.findtext("atom:content", "", ns) or item.findtext("description", "")
            pub_date = item.findtext("atom:published", "", ns) or item.findtext("pubDate", "")

            # Clean HTML from description
            desc_clean = re.sub(r"<[^>]+>", "", desc).strip()[:500]

            if title:
                signals.append({
                    "id": f"ph-{hash(link) & 0xFFFFFFFF:08x}",
                    "source": "producthunt",
                    "timestamp": pub_date or datetime.now(timezone.utc).isoformat(),
                    "author": "",
                    "title": title,
                    "content": desc_clean,
                    "url": link,
                    "metadata": {
                        "points": 0,  # RSS doesn't include upvotes
                        "relevance_tags": ["producthunt"],
                    }
                })
    except Exception as e:
        print(f"PH fetch error for {url}: {e}", file=sys.stderr)

    return signals


def main():
    all_signals = []
    seen = set()

    for url in CATEGORIES:
        print(f"Fetching {url}", file=sys.stderr)
        for s in fetch_rss(url):
            if s["id"] not in seen:
                seen.add(s["id"])
                all_signals.append(s)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "producthunt.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(all_signals, f, ensure_ascii=False, indent=2)

    print(f"Product Hunt: {len(all_signals)} signals → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
