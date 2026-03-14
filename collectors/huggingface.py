#!/usr/bin/env python3
"""HuggingFace collector — trending models and spaces."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

SIGNALS_DIR = Path(os.environ.get("SIGNALS_DIR", str(Path.home() / ".agenticEvolve" / "signals")))


def fetch_trending_models(limit: int = 20) -> list[dict]:
    """Fetch trending models from HuggingFace API."""
    signals = []
    url = f"https://huggingface.co/api/models?sort=likes&direction=-1&limit={limit}"
    try:
        req = Request(url, headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=15) as resp:
            models = json.loads(resp.read().decode("utf-8"))

        for m in models:
            model_id = m.get("modelId", "") or m.get("id", "")
            downloads = m.get("downloads", 0)
            likes = m.get("likes", 0)
            tags = m.get("tags", [])

            signals.append({
                "id": f"hf-model-{model_id.replace('/', '-')}",
                "source": "huggingface",
                "timestamp": m.get("lastModified", datetime.now(timezone.utc).isoformat()),
                "author": model_id.split("/")[0] if "/" in model_id else "",
                "title": f"[Model] {model_id}",
                "content": m.get("description", "") or f"Tags: {', '.join(tags[:5])}",
                "url": f"https://huggingface.co/{model_id}",
                "metadata": {
                    "points": likes,
                    "downloads": downloads,
                    "likes": likes,
                    "pipeline_tag": m.get("pipeline_tag", ""),
                    "relevance_tags": ["huggingface", "model"] + tags[:3],
                }
            })
    except Exception as e:
        print(f"HF models error: {e}", file=sys.stderr)
    return signals


def fetch_trending_spaces(limit: int = 15) -> list[dict]:
    """Fetch trending spaces from HuggingFace API."""
    signals = []
    url = f"https://huggingface.co/api/spaces?sort=likes&direction=-1&limit={limit}"
    try:
        req = Request(url, headers={"User-Agent": "agenticEvolve/1.0"})
        with urlopen(req, timeout=15) as resp:
            spaces = json.loads(resp.read().decode("utf-8"))

        for s in spaces:
            space_id = s.get("id", "")
            likes = s.get("likes", 0)

            signals.append({
                "id": f"hf-space-{space_id.replace('/', '-')}",
                "source": "huggingface",
                "timestamp": s.get("lastModified", datetime.now(timezone.utc).isoformat()),
                "author": space_id.split("/")[0] if "/" in space_id else "",
                "title": f"[Space] {space_id}",
                "content": s.get("description", "") or s.get("cardData", {}).get("title", ""),
                "url": f"https://huggingface.co/spaces/{space_id}",
                "metadata": {
                    "points": likes,
                    "likes": likes,
                    "sdk": s.get("sdk", ""),
                    "relevance_tags": ["huggingface", "space"],
                }
            })
    except Exception as e:
        print(f"HF spaces error: {e}", file=sys.stderr)
    return signals


def main():
    all_signals = []

    print("Fetching HuggingFace trending models...", file=sys.stderr)
    all_signals.extend(fetch_trending_models())

    print("Fetching HuggingFace trending spaces...", file=sys.stderr)
    all_signals.extend(fetch_trending_spaces())

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = SIGNALS_DIR / today
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "huggingface.json"

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(all_signals, f, ensure_ascii=False, indent=2)

    print(f"HuggingFace: {len(all_signals)} signals → {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
