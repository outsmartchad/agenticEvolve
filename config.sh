#!/bin/bash
# agenticEvolve configuration

# Load .env if present
if [ -f "$HOME/.agenticEvolve/.env" ]; then
    set -a
    source "$HOME/.agenticEvolve/.env"
    set +a
fi

# Cost caps
DAILY_CAP=5        # USD per day
WEEKLY_CAP=25      # USD per week

# Poll interval (used by documentation only — cron controls actual schedule)
POLL_INTERVAL="2h"

# Telegram bot (set these after creating bot via @BotFather)
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# Brave Search API (for X/Twitter signal collection)
BRAVE_API_KEY="${BRAVE_API_KEY:-}"

# Directories
EXODIR="$HOME/.agenticEvolve"
MEMORY="$EXODIR/memory"
SIGNALS="$EXODIR/signals"
LOGS="$EXODIR/logs"
QUEUE="$EXODIR/skills-queue"
SKILLS="$HOME/.claude/skills"
