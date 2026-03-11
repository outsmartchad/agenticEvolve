#!/bin/bash
# agenticEvolve — main cycle orchestrator
# ~150 lines. The intelligence is in the prompts, not here.
set -euo pipefail

EXODIR="$HOME/.agenticEvolve"
source "$EXODIR/config.sh"

TIMESTAMP=$(date +%Y-%m-%d_%H%M)
LOG="$LOGS/$TIMESTAMP.log"
mkdir -p "$LOGS"

log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG"; }

log "=== agenticEvolve cycle start ==="

# --- Cost check ---
TODAY=$(date +%Y-%m-%d)
TODAY_COST=$(grep "$TODAY" "$LOGS/cost.log" 2>/dev/null | awk '{sum+=$3} END{print sum+0}') || TODAY_COST="0"
if awk "BEGIN{exit !($TODAY_COST >= $DAILY_CAP)}"; then
    log "Daily cost cap reached (\$$TODAY_COST / \$$DAILY_CAP). Skipping."
    exit 0
fi

# --- 1. Collect signals ---
log "--- Collecting signals ---"

SIGNAL_COUNT=0

if bash "$EXODIR/collectors/github.sh" >> "$LOG" 2>&1; then
    GH_COUNT=$(cat "$SIGNALS/$TODAY"/github-*.json 2>/dev/null | jq -s 'flatten | length' 2>/dev/null) || GH_COUNT=0
    SIGNAL_COUNT=$((SIGNAL_COUNT + GH_COUNT))
    log "GitHub: $GH_COUNT signals"
else
    log "GitHub collector failed (continuing)"
fi

if bash "$EXODIR/collectors/hackernews.sh" >> "$LOG" 2>&1; then
    HN_COUNT=$(cat "$SIGNALS/$TODAY/hackernews.json" 2>/dev/null | jq -s 'length' 2>/dev/null) || HN_COUNT=0
    SIGNAL_COUNT=$((SIGNAL_COUNT + HN_COUNT))
    log "HN: $HN_COUNT signals"
else
    log "HN collector failed (continuing)"
fi

if bash "$EXODIR/collectors/x-search.sh" >> "$LOG" 2>&1; then
    X_COUNT=$(cat "$SIGNALS/$TODAY/x-search.json" 2>/dev/null | jq -s 'length' 2>/dev/null) || X_COUNT=0
    SIGNAL_COUNT=$((SIGNAL_COUNT + X_COUNT))
    log "X: $X_COUNT signals"
else
    log "X collector failed (continuing)"
fi

log "Total signals: $SIGNAL_COUNT"

if [ "$SIGNAL_COUNT" -eq 0 ]; then
    log "No signals collected. Skipping analysis."
    log "=== Cycle complete (no signals) ==="
    exit 0
fi

# --- 2. Analyze (fresh Claude instance) ---
log "--- Analyzing ---"

ANALYZE_OUTPUT=$(claude -p "$(cat $EXODIR/prompts/analyze.md)" \
    --model sonnet \
    --output-format stream-json \
    --verbose \
    --dangerously-skip-permissions \
    2>&1 | tee -a "$LOG") || true

# Log cost
ANALYZE_COST=$(echo "$ANALYZE_OUTPUT" | jq -sr '.[-1].total_cost_usd // "0"' 2>/dev/null || echo "0")
TODAY_COST=$(awk "BEGIN{print $TODAY_COST + $ANALYZE_COST}")
echo "$(date -Iseconds) analyze $ANALYZE_COST $TODAY_COST" >> "$LOGS/cost.log"
log "Analyze cost: \$$ANALYZE_COST (today: \$$TODAY_COST)"

# Extract text from stream-json for reliable promise detection
ANALYZE_TEXT=$(echo "$ANALYZE_OUTPUT" | jq -sr '[.[] | select(.type == "assistant" or .type == "result") | (.message.content[]?.text // .result // empty)] | join("\n")' 2>/dev/null || echo "$ANALYZE_OUTPUT")

# Check for nothing actionable
if echo "$ANALYZE_TEXT" | grep -q "<promise>NOTHING_ACTIONABLE</promise>"; then
    log "Nothing actionable this cycle."
    # Notify (silent by default, but log it)
    bash "$EXODIR/notify.sh" "cycle_summary" "$SIGNAL_COUNT" "0" "none" "$TODAY_COST" 2>/dev/null || true
    log "=== Cycle complete (nothing actionable) ==="
    exit 0
fi

# --- 3. Build one skill (fresh Claude instance) ---
log "--- Building skill ---"

BUILD_OUTPUT=$(claude -p "$(cat $EXODIR/prompts/build-skill.md)" \
    --model sonnet \
    --output-format stream-json \
    --verbose \
    --dangerously-skip-permissions \
    2>&1 | tee -a "$LOG") || true

# Log cost
BUILD_COST=$(echo "$BUILD_OUTPUT" | jq -sr '.[-1].total_cost_usd // "0"' 2>/dev/null || echo "0")
TODAY_COST=$(awk "BEGIN{print $TODAY_COST + $BUILD_COST}")
echo "$(date -Iseconds) build $BUILD_COST $TODAY_COST" >> "$LOGS/cost.log"
log "Build cost: \$$BUILD_COST (today: \$$TODAY_COST)"

# Extract text from stream-json
BUILD_TEXT=$(echo "$BUILD_OUTPUT" | jq -sr '[.[] | select(.type == "assistant" or .type == "result") | (.message.content[]?.text // .result // empty)] | join("\n")' 2>/dev/null || echo "$BUILD_OUTPUT")

# Check for build failure — log to memory
if echo "$BUILD_TEXT" | grep -q "<promise>BUILD_FAILED</promise>"; then
    log "Skill build FAILED"
    echo "" >> "$MEMORY/log.md"
    echo "## $(date -Iseconds) — BUILD_FAILED" >> "$MEMORY/log.md"
    echo "$BUILD_TEXT" | grep -A5 "BUILD_FAILED" | tail -5 >> "$MEMORY/log.md"
    echo "---" >> "$MEMORY/log.md"
    
    bash "$EXODIR/notify.sh" "build_failed" "$SIGNAL_COUNT" "0" "failed" "$TODAY_COST" 2>/dev/null || true
    log "=== Cycle complete (build failed) ==="
    exit 0
fi

# Get built skill name
SKILL_NAME=$(ls "$QUEUE/" 2>/dev/null | head -1 || echo "unknown")

# --- 4. Review skill (fresh Claude instance, Read-only) ---
if ls "$QUEUE/"*/SKILL.md 1>/dev/null 2>&1; then
    log "--- Reviewing skill: $SKILL_NAME ---"

    REVIEW_OUTPUT=$(claude -p "$(cat $EXODIR/prompts/review-skill.md)" \
        --model sonnet \
        --output-format stream-json \
        --verbose \
        --dangerously-skip-permissions \
        --allowedTools Read \
        2>&1 | tee -a "$LOG") || true

    REVIEW_COST=$(echo "$REVIEW_OUTPUT" | jq -sr '.[-1].total_cost_usd // "0"' 2>/dev/null || echo "0")
    TODAY_COST=$(awk "BEGIN{print $TODAY_COST + $REVIEW_COST}")
    echo "$(date -Iseconds) review $REVIEW_COST $TODAY_COST" >> "$LOGS/cost.log"
    log "Review cost: \$$REVIEW_COST (today: \$$TODAY_COST)"

    # If reviewer rejected, remove from queue and log
    # Extract text content from stream-json (ignore metadata like rate_limit_event)
    REVIEW_TEXT=$(echo "$REVIEW_OUTPUT" | jq -sr '[.[] | select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text] | join("\n")' 2>/dev/null || echo "$REVIEW_OUTPUT")
    if echo "$REVIEW_TEXT" | grep -qi "REJECTED"; then
        log "Skill $SKILL_NAME REJECTED by reviewer"
        REASON=$(echo "$REVIEW_TEXT" | grep -i "REJECTED" | head -1)
        echo "" >> "$MEMORY/log.md"
        echo "## $(date -Iseconds) — Skill Rejected: $SKILL_NAME" >> "$MEMORY/log.md"
        echo "- Reason: $REASON" >> "$MEMORY/log.md"
        echo "---" >> "$MEMORY/log.md"
        rm -rf "$QUEUE/$SKILL_NAME"
        SKILL_NAME="rejected:$SKILL_NAME"
    fi
fi

# --- 5. Notify via Telegram ---
bash "$EXODIR/notify.sh" "cycle_summary" "$SIGNAL_COUNT" "1" "$SKILL_NAME" "$TODAY_COST" 2>/dev/null || true

log "=== Cycle complete ==="
