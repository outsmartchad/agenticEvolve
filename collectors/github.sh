#!/bin/bash
# GitHub signal collector — uses gh CLI
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

TODAY=$(date +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

# 1. Trending repos (via GitHub search API — repos created/pushed recently with high stars)
echo "Collecting GitHub trending signals..."

gh api search/repositories \
    --method GET \
    -f q="stars:>20 pushed:>=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d '1 day ago' +%Y-%m-%d) topic:ai-agent OR topic:claude OR topic:mcp OR topic:agent-loop OR topic:dev-tools" \
    -f sort=stars \
    -f per_page=10 \
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
    }' > "$OUTDIR/github-trending.json" 2>/dev/null || echo "[]" > "$OUTDIR/github-trending.json"

# 2. Recent activity from starred repos
echo "Collecting starred repo activity..."

gh api user/starred \
    --method GET \
    -f per_page=20 \
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

# 3. Releases from key repos
echo "Collecting release signals..."

WATCH_REPOS=("anthropics/claude-code" "anthropics/claude-agent-sdk" "openclaw/openclaw" "snarktank/ralph")

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
done

[ -f "$OUTDIR/github-releases.json" ] || echo "[]" > "$OUTDIR/github-releases.json"

TOTAL=$(cat "$OUTDIR"/github-*.json 2>/dev/null | jq -s 'flatten | length')
echo "GitHub: $TOTAL signals collected"
