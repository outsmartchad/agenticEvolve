#!/bin/bash
# GitHub signal collector — uses gh CLI
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d '1 day ago' +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

echo "Collecting GitHub trending signals..."

# ── 1. Trending repos — multiple keyword groups to cast a wide net ──

SEARCH_QUERIES=(
    # AI / LLM / Agents
    "stars:>300 pushed:>=$YESTERDAY (ai-agent OR llm OR RAG OR vector-database OR embedding)"
    "stars:>300 pushed:>=$YESTERDAY (claude OR mcp OR openai OR anthropic OR gemini)"
    "stars:>200 pushed:>=$YESTERDAY (agent-loop OR agentic OR autonomous-agent OR multi-agent)"
    # Developer tools & infrastructure
    "stars:>500 pushed:>=$YESTERDAY (developer-tools OR devtools OR CLI OR terminal)"
    "stars:>300 pushed:>=$YESTERDAY (typescript OR react OR nextjs OR svelte OR vue)"
    "stars:>300 pushed:>=$YESTERDAY (rust OR golang OR systems-programming)"
    # Hot new repos (created recently, growing fast)
    "stars:>100 created:>=$YESTERDAY language:TypeScript"
    "stars:>100 created:>=$YESTERDAY language:Python"
    "stars:>100 created:>=$YESTERDAY language:Rust"
    # Infrastructure & databases
    "stars:>300 pushed:>=$YESTERDAY (database OR orm OR serverless OR edge-computing)"
    "stars:>300 pushed:>=$YESTERDAY (browser-automation OR web-scraping OR crawler)"
    # Coding tools & AI coding
    "stars:>200 pushed:>=$YESTERDAY (code-editor OR lsp OR copilot OR cursor OR coding-agent)"
    # Blockchain / onchain (Vincent's domain)
    "stars:>200 pushed:>=$YESTERDAY (solana OR ethereum OR onchain OR defi OR smart-contract)"
)

> "$OUTDIR/github-trending.json"

for query in "${SEARCH_QUERIES[@]}"; do
    gh api search/repositories \
        --method GET \
        -f q="$query" \
        -f sort=stars \
        -f per_page=5 \
        --jq '.items[] | {
            id: ("github-repo-" + (.id | tostring)),
            source: "github",
            timestamp: .updated_at,
            author: .owner.login,
            title: .full_name,
            content: (.description // "No description"),
            url: .html_url,
            metadata: {
                stars: .stargazers_count,
                forks: .forks_count,
                language: .language,
                relevance_tags: [.topics[]?]
            }
        }' >> "$OUTDIR/github-trending.json" 2>/dev/null || true
    sleep 0.3
done

# Deduplicate by repo ID
if [ -s "$OUTDIR/github-trending.json" ]; then
    jq -s 'unique_by(.id)' "$OUTDIR/github-trending.json" > "$OUTDIR/github-trending.tmp" 2>/dev/null && \
        mv "$OUTDIR/github-trending.tmp" "$OUTDIR/github-trending.json" || true
fi

# ── 2. Recent activity from starred repos ──

echo "Collecting starred repo activity..."

gh api user/starred \
    --method GET \
    -f per_page=30 \
    -f sort=updated \
    --jq '.[] | select(.pushed_at > (now - 86400 | strftime("%Y-%m-%dT%H:%M:%SZ"))) | {
        id: ("github-starred-" + (.id | tostring)),
        source: "github",
        timestamp: .pushed_at,
        author: .owner.login,
        title: .full_name,
        content: (.description // "No description"),
        url: .html_url,
        metadata: {
            stars: .stargazers_count,
            relevance_tags: ["starred"]
        }
    }' > "$OUTDIR/github-starred.json" 2>/dev/null || echo "[]" > "$OUTDIR/github-starred.json"

# ── 3. Releases from watched repos ──

echo "Collecting release signals..."

WATCH_REPOS=(
    # Claude ecosystem
    "anthropics/claude-code"
    "anthropics/anthropic-sdk-python"
    "anthropics/courses"
    # AI agents & tools
    "langchain-ai/langgraph"
    "microsoft/autogen"
    "openai/codex"
    "vercel/ai"
    "jina-ai/reader"
    # Dev tools
    "oven-sh/bun"
    "denoland/deno"
    "biomejs/biome"
    "tailwindlabs/tailwindcss"
    # Databases & infra
    "drizzle-team/drizzle-orm"
    "turso-tech/libsql"
    # Blockchain
    "solana-labs/solana"
    "coral-xyz/anchor"
)

> "$OUTDIR/github-releases.json"

for repo in "${WATCH_REPOS[@]}"; do
    gh api "repos/$repo/releases" \
        --method GET \
        -f per_page=3 \
        --jq '.[] | select(.published_at > (now - 604800 | strftime("%Y-%m-%dT%H:%M:%SZ"))) | {
            id: ("github-release-" + (.id | tostring)),
            source: "github",
            timestamp: .published_at,
            author: .author.login,
            title: ("Release: " + .tag_name + " — " + (.name // "")),
            content: (.body // "No release notes" | .[0:500]),
            url: .html_url,
            metadata: {
                repo: "'"$repo"'",
                tag: .tag_name,
                relevance_tags: ["release"]
            }
        }' >> "$OUTDIR/github-releases.json" 2>/dev/null || true
    sleep 0.2
done

[ -s "$OUTDIR/github-releases.json" ] || echo "[]" > "$OUTDIR/github-releases.json"

TOTAL=$(cat "$OUTDIR"/github-*.json 2>/dev/null | jq -s 'flatten | length')
echo "GitHub: $TOTAL signals collected"
