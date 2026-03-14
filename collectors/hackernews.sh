#!/bin/bash
# Hacker News signal collector — uses Algolia API
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

TODAY=$(date +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

# Broad keyword groups across tech domains
KEYWORDS=(
    # AI / LLM / Agents
    "claude+code"
    "AI+agent"
    "LLM+open+source"
    "RAG+vector+database"
    "agentic+workflow"
    "coding+agent+copilot"
    "mcp+server"
    # Developer tools
    "developer+tools+release"
    "CLI+tool+new"
    "open+source+launch"
    # Languages & frameworks
    "typescript+framework"
    "rust+release"
    "react+nextjs"
    "bun+deno+runtime"
    "svelte+vue"
    # Infrastructure
    "database+new+release"
    "serverless+edge"
    "browser+automation"
    "web+scraping"
    # Blockchain
    "solana+ethereum"
    "smart+contract+defi"
    # General
    "startup+launch+YC"
    "programming+language"
    "performance+benchmark"
)

echo "Collecting Hacker News signals (${#KEYWORDS[@]} queries)..."

> "$OUTDIR/hackernews.json"

for keyword in "${KEYWORDS[@]}"; do
    curl -sL "https://hn.algolia.com/api/v1/search?query=$keyword&tags=story&numericFilters=points%3E20&hitsPerPage=5" \
        | jq '.hits[] | {
            id: ("hn-" + .objectID),
            source: "hn",
            timestamp: .created_at,
            author: .author,
            title: .title,
            content: (.story_text // .title),
            url: (.url // ("https://news.ycombinator.com/item?id=" + .objectID)),
            metadata: {
                points: .points,
                replies: .num_comments,
                relevance_tags: ["'"${keyword//+/-}"'"]
            }
        }' >> "$OUTDIR/hackernews.json" 2>/dev/null || true
    sleep 0.3
done

# HN front page (high engagement, any topic)
echo "Collecting HN front page..."
curl -sL "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=20" \
    | jq '.hits[] | {
        id: ("hn-front-" + .objectID),
        source: "hn",
        timestamp: .created_at,
        author: .author,
        title: .title,
        content: (.story_text // .title),
        url: (.url // ("https://news.ycombinator.com/item?id=" + .objectID)),
        metadata: {
            points: .points,
            replies: .num_comments,
            relevance_tags: ["front-page"]
        }
    }' >> "$OUTDIR/hackernews.json" 2>/dev/null || true

# Show HN with traction
echo "Collecting Show HN..."
curl -sL "https://hn.algolia.com/api/v1/search?tags=show_hn&numericFilters=points%3E15&hitsPerPage=15" \
    | jq '.hits[] | {
        id: ("hn-show-" + .objectID),
        source: "hn",
        timestamp: .created_at,
        author: .author,
        title: .title,
        content: (.story_text // .title),
        url: (.url // ("https://news.ycombinator.com/item?id=" + .objectID)),
        metadata: {
            points: .points,
            replies: .num_comments,
            relevance_tags: ["show-hn"]
        }
    }' >> "$OUTDIR/hackernews.json" 2>/dev/null || true

# Deduplicate
if [ -s "$OUTDIR/hackernews.json" ]; then
    jq -s 'unique_by(.id)' "$OUTDIR/hackernews.json" > "$OUTDIR/hackernews.tmp" 2>/dev/null && \
        mv "$OUTDIR/hackernews.tmp" "$OUTDIR/hackernews.json" || true
fi

TOTAL=$(jq -s 'if type == "array" and length > 0 and (.[0] | type) == "array" then .[0] | length else length end' "$OUTDIR/hackernews.json" 2>/dev/null || echo 0)
echo "Hacker News: $TOTAL signals collected"
