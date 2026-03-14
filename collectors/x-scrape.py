#!/usr/bin/env python3
"""
X (Twitter) signal collector via browser scraping.

Fallback collector when Brave API key isn't available.
Uses Playwright to scrape X search results for viral tech content.

Usage:
    python3 x-scrape.py                    # default queries
    python3 x-scrape.py --query "AI agent" # custom query

Requires: playwright (pip install playwright && playwright install chromium)
"""

import json
import os
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))
BROWSER_PROFILE = Path.home() / ".agenticEvolve" / "browser-profiles" / "x-scraper"

# Search queries for trending tech on X
DEFAULT_QUERIES = [
    "open source github.com viral min_faves:100",
    "AI agent tool release github min_faves:50",
    "new developer tool launch 2026 min_faves:50",
    "claude code OR cursor OR codex update min_faves:100",
    "just open sourced github.com min_faves:50",
    "LLM framework release min_faves:50",
]

MAX_TWEETS_PER_QUERY = 10


def scrape_x_search(query: str, max_tweets: int = MAX_TWEETS_PER_QUERY) -> list[dict]:
    """Scrape X search results for a query using Playwright."""
    from playwright.sync_api import sync_playwright

    tweets = []

    try:
        with sync_playwright() as p:
            # Use persistent context to keep cookies/login across runs
            BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.pages[0] if browser.pages else browser.new_page()

            # Navigate to X search
            search_url = f"https://x.com/search?q={query}&src=typed_query&f=top"
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")

            # Wait for tweets to load
            try:
                page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
            except Exception:
                # Maybe login wall or no results
                browser.close()
                return []

            # Scroll to load more
            for _ in range(2):
                page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(1.5)

            # Extract tweets
            tweet_elements = page.query_selector_all('[data-testid="tweet"]')

            for el in tweet_elements[:max_tweets]:
                try:
                    # Get tweet text
                    text_el = el.query_selector('[data-testid="tweetText"]')
                    text = text_el.inner_text() if text_el else ""

                    # Get author
                    user_el = el.query_selector('a[role="link"][href*="/"]')
                    author = ""
                    author_url = ""
                    if user_el:
                        href = user_el.get_attribute("href") or ""
                        author = href.strip("/").split("/")[-1] if href else ""
                        author_url = f"https://x.com{href}" if href else ""

                    # Get tweet link
                    time_el = el.query_selector("time")
                    tweet_url = ""
                    if time_el:
                        parent_a = time_el.evaluate("el => el.closest('a')?.href")
                        tweet_url = parent_a or ""

                    # Get timestamp
                    tweet_time = ""
                    if time_el:
                        tweet_time = time_el.get_attribute("datetime") or ""

                    # Extract any URLs in the tweet
                    links = el.query_selector_all('a[href*="http"]')
                    external_urls = []
                    for link in links:
                        href = link.get_attribute("href") or ""
                        if href and "x.com" not in href and "twitter.com" not in href:
                            external_urls.append(href)

                    # Get engagement metrics (likes, retweets)
                    metrics = el.query_selector_all('[data-testid$="count"]')
                    engagement = 0
                    for m in metrics:
                        try:
                            val = m.inner_text().strip()
                            if val:
                                # Handle "1.2K", "5M" etc
                                val = val.replace(",", "")
                                if "K" in val:
                                    engagement += int(float(val.replace("K", "")) * 1000)
                                elif "M" in val:
                                    engagement += int(float(val.replace("M", "")) * 1000000)
                                else:
                                    engagement += int(val)
                        except (ValueError, TypeError):
                            pass

                    if text:
                        tweets.append({
                            "id": f"x-{author}-{hash(text) & 0xFFFFFFFF:08x}",
                            "source": "x",
                            "timestamp": tweet_time or datetime.now(timezone.utc).isoformat(),
                            "author": author,
                            "title": text[:120] + ("..." if len(text) > 120 else ""),
                            "content": text,
                            "url": tweet_url,
                            "metadata": {
                                "engagement": engagement,
                                "points": engagement,  # for ranking in evolve pipeline
                                "external_urls": external_urls,
                                "query": query,
                                "relevance_tags": ["x-scrape"],
                            }
                        })
                except Exception:
                    continue

            browser.close()

    except Exception as e:
        print(f"Scrape error for query '{query}': {e}", file=sys.stderr)

    return tweets


def main():
    import argparse
    parser = argparse.ArgumentParser(description="X/Twitter signal scraper")
    parser.add_argument("--query", type=str, help="Custom search query (overrides defaults)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window")
    args = parser.parse_args()

    queries = [args.query] if args.query else DEFAULT_QUERIES

    all_tweets = []
    seen_ids = set()

    for q in queries:
        print(f"Scraping X: {q}", file=sys.stderr)
        tweets = scrape_x_search(q)
        for t in tweets:
            if t["id"] not in seen_ids:
                seen_ids.add(t["id"])
                all_tweets.append(t)
        print(f"  Found {len(tweets)} tweets", file=sys.stderr)
        time.sleep(1)  # rate limit between queries

    # Write to signals dir
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "x-scrape.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(all_tweets, f, ensure_ascii=False, indent=2)

    print(f"X (scrape): {len(all_tweets)} signals collected → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
