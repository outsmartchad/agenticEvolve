#!/bin/bash
# X (Twitter) signal collector — uses Brave Search API with site:x.com
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

if [ -z "$BRAVE_API_KEY" ]; then
    echo "BRAVE_API_KEY not set. Skipping X collection."
    exit 0
fi

TODAY=$(date +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

# Search queries — site:x.com scoped
QUERIES=(
    "site:x.com+claude+code+skill+OR+mcp+OR+agent"
    "site:x.com+from:AnthropicAI+OR+from:alexalbert__"
    "site:x.com+harness+engineering+AI+agent"
    "site:x.com+agentic+workflow+developer+tools"
)

echo "Collecting X signals via Brave Search..."

> "$OUTDIR/x-search.json"

for query in "${QUERIES[@]}"; do
    curl -s "https://api.search.brave.com/res/v1/web/search?q=$(echo "$query" | sed 's/+/%2B/g; s/ /+/g')&count=5&freshness=pw" \
        -H "X-Subscription-Token: $BRAVE_API_KEY" \
        | jq '.web.results[]? | {
            id: ("x-" + (.url | gsub("[^a-zA-Z0-9]"; "") | .[0:32])),
            source: "x",
            timestamp: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
            author: (.url | capture("x\\.com/(?<user>[^/]+)").user // "unknown"),
            title: .title,
            content: .description,
            url: .url,
            metadata: {
                relevance_tags: ["x-search"]
            }
        }' >> "$OUTDIR/x-search.json" 2>/dev/null || true
    
    sleep 0.5
done

TOTAL=$(cat "$OUTDIR/x-search.json" 2>/dev/null | jq -s 'length')
echo "X (Brave Search): $TOTAL signals collected"
