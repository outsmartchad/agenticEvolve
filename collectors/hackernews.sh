#!/bin/bash
# Hacker News signal collector — uses Algolia API
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

TODAY=$(date +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

# Keywords to search
KEYWORDS=("claude+code" "mcp+server" "agent+loop" "agentic+workflow" "harness+engineering" "ai+coding+agent" "dev+tools+ai" "claude+skills")

echo "Collecting Hacker News signals..."

> "$OUTDIR/hackernews.json"

for keyword in "${KEYWORDS[@]}"; do
    curl -sL "https://hn.algolia.com/api/v1/search_by_date?query=$keyword&tags=story&numericFilters=points%3E30&hitsPerPage=5" \
        | jq '.hits[] | {
            id: ("hn-" + .objectID),
            source: "hn",
            timestamp: .created_at,
            author: .author,
            title: .title,
            content: (.story_text // .title),
            url: ("https://news.ycombinator.com/item?id=" + .objectID),
            metadata: {
                points: .points,
                replies: .num_comments,
                relevance_tags: ["'"${keyword//+/-}"'"]
            }
        }' >> "$OUTDIR/hackernews.json" 2>/dev/null || true
    
    # Rate limit: don't hammer the API
    sleep 0.5
done

# Also grab Show HN posts with decent traction
curl -sL "https://hn.algolia.com/api/v1/search_by_date?query=show+hn&tags=show_hn&numericFilters=points%3E20&hitsPerPage=10" \
    | jq '.hits[] | {
        id: ("hn-show-" + .objectID),
        source: "hn",
        timestamp: .created_at,
        author: .author,
        title: .title,
        content: (.story_text // .title),
        url: ("https://news.ycombinator.com/item?id=" + .objectID),
        metadata: {
            points: .points,
            replies: .num_comments,
            relevance_tags: ["show-hn"]
        }
    }' >> "$OUTDIR/hackernews.json" 2>/dev/null || true

TOTAL=$(cat "$OUTDIR/hackernews.json" 2>/dev/null | jq -s 'length')
echo "Hacker News: $TOTAL signals collected"
