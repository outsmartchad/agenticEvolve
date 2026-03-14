#!/usr/bin/env python3
"""ArXiv collector — fetches recent papers from cs.AI, cs.CL, cs.SE."""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))

# ArXiv categories: AI, Computation and Language (NLP/LLM), Software Engineering
CATEGORIES = ["cs.AI", "cs.CL", "cs.SE", "cs.LG"]

# Keywords to boost relevance (papers matching these get higher priority)
BOOST_KEYWORDS = [
    "agent", "llm", "code generation", "tool use", "reasoning",
    "retrieval", "embedding", "benchmark", "open source",
    "typescript", "compiler", "developer", "programming",
]


def fetch_arxiv(category: str, max_results: int = 15) -> list[dict]:
    """Fetch recent papers from ArXiv API."""
    signals = []
    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={max_results}"
    )

    try:
        req = Request(url, headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8")

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        root = ET.fromstring(data)

        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
            summary = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")[:500]
            published = entry.findtext("atom:published", "", ns)
            arxiv_id = entry.findtext("atom:id", "", ns).split("/")[-1]
            
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += f" +{len(authors) - 3}"

            link = f"https://arxiv.org/abs/{arxiv_id}"

            # Relevance boost
            text_lower = (title + " " + summary).lower()
            boost = sum(1 for kw in BOOST_KEYWORDS if kw in text_lower)

            signals.append({
                "id": f"arxiv-{arxiv_id}",
                "source": "arxiv",
                "timestamp": published,
                "author": author_str,
                "title": f"[{category}] {title}",
                "content": summary,
                "url": link,
                "metadata": {
                    "points": boost * 10,  # keyword matches as engagement proxy
                    "category": category,
                    "arxiv_id": arxiv_id,
                    "relevance_tags": ["arxiv", category],
                }
            })
    except Exception as e:
        print(f"ArXiv {category} error: {e}", file=sys.stderr)

    return signals


def main():
    all_signals = []
    seen = set()

    for cat in CATEGORIES:
        print(f"Fetching arxiv {cat}...", file=sys.stderr)
        for s in fetch_arxiv(cat):
            if s["id"] not in seen:
                seen.add(s["id"])
                all_signals.append(s)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "arxiv.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(all_signals, f, ensure_ascii=False, indent=2)

    print(f"ArXiv: {len(all_signals)} papers across {len(CATEGORIES)} categories → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
