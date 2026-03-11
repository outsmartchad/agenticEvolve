#!/bin/bash
# agenticEvolve — weekly garbage collection
set -euo pipefail

EXODIR="$HOME/.agenticEvolve"
source "$EXODIR/config.sh"

LOG="$LOGS/gc-$(date +%Y-%m-%d).log"
mkdir -p "$LOGS"

echo "[$(date +%H:%M:%S)] === Garbage Collection ===" >> "$LOG"

claude -p "$(cat $EXODIR/prompts/gc.md)" \
    --model sonnet \
    --output-format stream-json \
    --dangerously-skip-permissions \
    --print >> "$LOG" 2>&1 || true

echo "[$(date +%H:%M:%S)] === GC complete ===" >> "$LOG"

# Notify
bash "$EXODIR/notify.sh" "gc_complete" 2>/dev/null || true
