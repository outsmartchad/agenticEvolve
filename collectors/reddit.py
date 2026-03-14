#!/usr/bin/env python3
"""Reddit collector — fetches top posts via Pullpush.io API (Reddit archive, bypasses VPN blocks)."""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))

SUBREDDITS = [
    "LocalLLaMA",
    "MachineLearning",
    "programming",
    "SideProject",
    "selfhosted",
    "opensource",
    "rust",
    "typescript",
    "reactjs",
    "nextjs",
    "solana",
    "ChatGPTCoding",
    "ClaudeAI",
]

MIN_SCORE = 0  # Pullpush scores lag, so accept all posts
POSTS_PER_SUB = 10


def fetch_subreddit(name: str) -> list[dict]:
    """Fetch recent top posts from a subreddit via Pullpush.io API."""
    signals = []
    # Get recent posts sorted by newest (Pullpush scores lag behind Reddit)
    url = (
        f"https://api.pullpush.io/reddit/search/submission/"
        f"?subreddit={name}&size={POSTS_PER_SUB}&sort=created_utc&sort_type=desc"
    )

    try:
        req = Request(url, headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for post in data.get("data", []):
            score = post.get("score", 0)
            if score < MIN_SCORE:
                continue

            title = post.get("title", "")
            selftext = post.get("selftext", "")[:500]
            link = post.get("url", "")
            permalink = f"https://reddit.com{post.get('permalink', '')}"
            created = post.get("created_utc", 0)

            signals.append({
                "id": f"reddit-{post.get('id', '')}",
                "source": "reddit",
                "timestamp": datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else "",
                "author": post.get("author", ""),
                "title": f"[r/{name}] {title}",
                "content": selftext or title,
                "url": permalink,
                "metadata": {
                    "points": score,
                    "replies": post.get("num_comments", 0),
                    "subreddit": name,
                    "external_url": link if link != permalink else "",
                    "relevance_tags": [f"r/{name}"],
                }
            })
    except Exception as e:
        print(f"Reddit r/{name} error: {e}", file=sys.stderr)

    return signals


def main():
    all_signals = []
    seen = set()

    for sub in SUBREDDITS:
        print(f"Fetching r/{sub}...", file=sys.stderr)
        for s in fetch_subreddit(sub):
            if s["id"] not in seen:
                seen.add(s["id"])
                all_signals.append(s)
        time.sleep(0.5)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "reddit.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(all_signals, f, ensure_ascii=False, indent=2)

    print(f"Reddit: {len(all_signals)} signals across {len(SUBREDDITS)} subreddits → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
