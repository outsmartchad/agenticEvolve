#!/usr/bin/env python3
"""BestOfJS collector — tracks trending JavaScript/TypeScript projects."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))


def fetch_bestofjs() -> list[dict]:
    """Fetch trending projects from BestOfJS API."""
    signals = []
    # BestOfJS has a public JSON snapshot of trending projects
    url = "https://bestofjs-static-api.vercel.app/projects.json"

    try:
        req = Request(url, headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        projects = data.get("projects", [])

        # Sort by daily trend (stars added today)
        for p in projects:
            trends = p.get("trends", {})
            p["_daily"] = trends.get("daily", 0)

        projects.sort(key=lambda x: x.get("_daily", 0), reverse=True)

        for p in projects[:30]:
            name = p.get("name", "")
            full_name = p.get("full_name", "")
            desc = p.get("description", "")
            stars = p.get("stars", 0)
            daily = p.get("_daily", 0)
            tags = p.get("tags", [])
            url_proj = p.get("url", "") or f"https://github.com/{full_name}" if full_name else ""

            if daily < 5:  # skip if not actually trending
                continue

            signals.append({
                "id": f"bestofjs-{name}",
                "source": "bestofjs",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "author": full_name.split("/")[0] if "/" in full_name else "",
                "title": f"{full_name or name} (+{daily}/day)",
                "content": desc,
                "url": url_proj,
                "metadata": {
                    "stars": stars,
                    "stars_today": daily,
                    "points": daily,  # for ranking
                    "tags": tags,
                    "relevance_tags": ["bestofjs"] + tags[:3],
                }
            })
    except Exception as e:
        print(f"BestOfJS error: {e}", file=sys.stderr)

    return signals


def main():
    signals = fetch_bestofjs()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "bestofjs.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print(f"BestOfJS: {len(signals)} trending JS/TS projects → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
