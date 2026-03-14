#!/usr/bin/env python3
"""GitHub Trending collector — uses gh CLI (authenticated) to find today's hottest repos."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))

# Broader trending queries — repos created in last 7 days with fast star growth
QUERIES = [
    # Overall hot new repos
    "stars:>50 created:>{week_ago}",
    # By language
    "stars:>30 created:>{week_ago} language:Python",
    "stars:>30 created:>{week_ago} language:TypeScript",
    "stars:>30 created:>{week_ago} language:Rust",
    "stars:>30 created:>{week_ago} language:Go",
    # AI specific
    "stars:>20 created:>{week_ago} topic:llm OR topic:ai OR topic:agent",
]


def fetch_trending() -> list[dict]:
    """Use gh CLI to search for trending repos."""
    signals = []
    seen = set()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    for query_template in QUERIES:
        query = query_template.replace("{week_ago}", week_ago)
        try:
            result = subprocess.run(
                ["gh", "api", "search/repositories",
                 "--method", "GET",
                 "-f", f"q={query}",
                 "-f", "sort=stars",
                 "-f", "per_page=10"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                continue

            data = json.loads(result.stdout)
            for item in data.get("items", []):
                repo_id = item.get("full_name", "")
                if repo_id in seen:
                    continue
                seen.add(repo_id)

                signals.append({
                    "id": f"gh-trending-{repo_id.replace('/', '-')}",
                    "source": "github-trending",
                    "timestamp": item.get("created_at", ""),
                    "author": item.get("owner", {}).get("login", ""),
                    "title": repo_id,
                    "content": item.get("description", "") or "No description",
                    "url": item.get("html_url", ""),
                    "metadata": {
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "points": item.get("stargazers_count", 0),
                        "language": item.get("language", ""),
                        "topics": item.get("topics", [])[:5],
                        "relevance_tags": ["github-trending"],
                    }
                })
        except Exception as e:
            print(f"GitHub trending query error: {e}", file=sys.stderr)

    # Sort by stars descending
    signals.sort(key=lambda x: x["metadata"]["stars"], reverse=True)
    return signals[:50]  # cap at 50


def main():
    print("Fetching GitHub trending via gh CLI...", file=sys.stderr)
    signals = fetch_trending()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "github-trending-page.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print(f"GitHub Trending: {len(signals)} hot new repos → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
