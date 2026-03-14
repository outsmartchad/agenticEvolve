#!/bin/bash
# X (Twitter) signal collector — uses Brave Search API with site:x.com
# Expanded queries to catch viral open-source repos, new dev tools, and tech trends
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

if [ -z "$BRAVE_API_KEY" ]; then
    echo "BRAVE_API_KEY not set. Skipping X collection."
    exit 0
fi

TODAY=$(date +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

# Search queries — site:x.com scoped, covering:
#   1. AI agents & Claude ecosystem
#   2. Viral open-source repos (github.com links on X)
#   3. New developer tools & frameworks
#   4. Key AI/dev influencers
#   5. Trending tech articles shared on X
QUERIES=(
    # AI agents & Claude
    "site:x.com claude code OR claude agent OR mcp server"
    "site:x.com from:AnthropicAI OR from:alexalbert__ OR from:aaboreal"
    # Viral open-source repos shared on X
    "site:x.com github.com open source viral OR trending OR star"
    "site:x.com github.com new release AI OR LLM OR agent"
    "site:x.com just open sourced OR just released github"
    # Developer tools & frameworks
    "site:x.com developer tool launch OR release 2026"
    "site:x.com new framework typescript OR react OR nextjs"
    "site:x.com cursor OR windsurf OR codex OR copilot update"
    # AI dev influencers sharing tools
    "site:x.com from:karpathy OR from:swyx OR from:aiaboreal"
    "site:x.com from:levelsio OR from:mcaboreal OR from:raaboreal"
    # Viral tech content
    "site:x.com built this with AI open source github"
    "site:x.com AI coding agent benchmark OR comparison"
)

echo "Collecting X signals via Brave Search (${#QUERIES[@]} queries)..."

> "$OUTDIR/x-search.json"

SEEN_URLS=""

for query in "${QUERIES[@]}"; do
    # URL-encode the query
    ENCODED=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$query" 2>/dev/null || echo "$query" | sed 's/ /+/g')
    
    RESULT=$(curl -s "https://api.search.brave.com/res/v1/web/search?q=${ENCODED}&count=8" \
        -H "X-Subscription-Token: $BRAVE_API_KEY" \
        -H "Accept: application/json" 2>/dev/null || echo '{}')
    
    echo "$RESULT" | jq -r '.web.results[]? | {
            id: ("x-" + (.url | gsub("[^a-zA-Z0-9]"; "") | .[0:40])),
            source: "x",
            timestamp: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
            author: (.url | capture("x\\.com/(?<user>[^/]+)").user // "unknown"),
            title: .title,
            content: .description,
            url: .url,
            metadata: {
                relevance_tags: ["x-search"],
                query: "'"$(echo "$query" | sed 's/site:x.com //')"'"
            }
        }' >> "$OUTDIR/x-search.json" 2>/dev/null || true
    
    sleep 0.3
done

# Deduplicate by URL
if [ -s "$OUTDIR/x-search.json" ]; then
    jq -s 'unique_by(.url)' "$OUTDIR/x-search.json" > "$OUTDIR/x-search.tmp.json" 2>/dev/null && \
        mv "$OUTDIR/x-search.tmp.json" "$OUTDIR/x-search.json" || true
fi

TOTAL=$(cat "$OUTDIR/x-search.json" 2>/dev/null | jq -s 'if type == "array" and (.[0] | type) == "array" then .[0] | length else length end' 2>/dev/null || echo 0)
echo "X (Brave Search): $TOTAL signals collected"
