#!/bin/bash
# agenticEvolve — Telegram callback listener
# Polls for approve/reject button presses
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config.sh"
    exit 1
fi

OFFSET_FILE="$HOME/.agenticEvolve/logs/.telegram_offset"
OFFSET=$(cat "$OFFSET_FILE" 2>/dev/null || echo "0")

echo "agenticEvolve Telegram listener started (offset: $OFFSET)"
echo "Listening for approve/reject callbacks..."

while true; do
    # Get updates
    RESPONSE=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=$OFFSET&timeout=30" 2>/dev/null)

    # Process each update
    echo "$RESPONSE" | jq -c '.result[]?' 2>/dev/null | while IFS= read -r update; do
        UPDATE_ID=$(echo "$update" | jq -r '.update_id')
        OFFSET=$((UPDATE_ID + 1))
        echo "$OFFSET" > "$OFFSET_FILE"

        # Check for callback query (button press)
        CALLBACK_DATA=$(echo "$update" | jq -r '.callback_query.data // empty')
        CALLBACK_ID=$(echo "$update" | jq -r '.callback_query.id // empty')

        if [ -n "$CALLBACK_DATA" ]; then
            ACTION=$(echo "$CALLBACK_DATA" | cut -d: -f1)
            SKILL=$(echo "$CALLBACK_DATA" | cut -d: -f2)

            case "$ACTION" in
                approve)
                    if [ -d "$HOME/.agenticEvolve/skills-queue/$SKILL" ]; then
                        mkdir -p "$HOME/.claude/skills/$SKILL"
                        mv "$HOME/.agenticEvolve/skills-queue/$SKILL/"* "$HOME/.claude/skills/$SKILL/"
                        rmdir "$HOME/.agenticEvolve/skills-queue/$SKILL"
                        
                        echo "## $(date -Iseconds) — Skill Approved: $SKILL" >> "$HOME/.agenticEvolve/memory/log.md"
                        echo "---" >> "$HOME/.agenticEvolve/memory/log.md"

                        # Answer callback
                        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/answerCallbackQuery" \
                            -d callback_query_id="$CALLBACK_ID" \
                            -d text="✅ $SKILL approved and installed" > /dev/null

                        # Send confirmation
                        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
                            -d chat_id="$TELEGRAM_CHAT_ID" \
                            -d text="✅ Skill \`$SKILL\` approved and moved to ~/.claude/skills/" \
                            -d parse_mode="Markdown" > /dev/null

                        echo "[$(date +%H:%M:%S)] Approved: $SKILL"
                    else
                        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/answerCallbackQuery" \
                            -d callback_query_id="$CALLBACK_ID" \
                            -d text="Skill not found in queue" > /dev/null
                    fi
                    ;;

                reject)
                    if [ -d "$HOME/.agenticEvolve/skills-queue/$SKILL" ]; then
                        rm -rf "$HOME/.agenticEvolve/skills-queue/$SKILL"

                        echo "## $(date -Iseconds) — Skill Rejected via Telegram: $SKILL" >> "$HOME/.agenticEvolve/memory/log.md"
                        echo "---" >> "$HOME/.agenticEvolve/memory/log.md"

                        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/answerCallbackQuery" \
                            -d callback_query_id="$CALLBACK_ID" \
                            -d text="❌ $SKILL rejected" > /dev/null

                        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
                            -d chat_id="$TELEGRAM_CHAT_ID" \
                            -d text="❌ Skill \`$SKILL\` rejected and removed from queue" \
                            -d parse_mode="Markdown" > /dev/null

                        echo "[$(date +%H:%M:%S)] Rejected: $SKILL"
                    else
                        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/answerCallbackQuery" \
                            -d callback_query_id="$CALLBACK_ID" \
                            -d text="Skill not found in queue" > /dev/null
                    fi
                    ;;
            esac
        fi
    done

    # Update offset for next poll
    LATEST=$(echo "$RESPONSE" | jq -r '.result[-1].update_id // empty' 2>/dev/null)
    if [ -n "$LATEST" ]; then
        OFFSET=$((LATEST + 1))
        echo "$OFFSET" > "$OFFSET_FILE"
    fi
done
