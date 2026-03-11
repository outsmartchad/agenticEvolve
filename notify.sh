#!/bin/bash
# agenticEvolve — Telegram notification
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

# Skip if Telegram not configured
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    exit 0
fi

send() {
    curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$1" \
        -d parse_mode="Markdown" > /dev/null 2>&1
}

send_with_keyboard() {
    curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$1" \
        -d parse_mode="Markdown" \
        -d reply_markup="$2" > /dev/null 2>&1
}

TYPE="${1:-}"

case "$TYPE" in
    cycle_summary)
        SIGNALS="${2:-0}"
        SKILLS_BUILT="${3:-0}"
        SKILL_NAME="${4:-none}"
        COST="${5:-0}"

        if [ "$SKILL_NAME" = "none" ]; then
            send "$(cat <<EOF
🔄 *agenticEvolve cycle complete*
📡 Signals: $SIGNALS
📋 Nothing actionable
💰 Cost today: \$$COST
EOF
)"
        elif echo "$SKILL_NAME" | grep -q "^rejected:"; then
            REJECTED_NAME="${SKILL_NAME#rejected:}"
            send "$(cat <<EOF
🔄 *agenticEvolve cycle complete*
📡 Signals: $SIGNALS
❌ Skill rejected: \`$REJECTED_NAME\`
💰 Cost today: \$$COST
EOF
)"
        else
            # Skill built — send with approve/reject buttons
            SKILL_PREVIEW=$(head -20 "$HOME/.agenticEvolve/skills-queue/$SKILL_NAME/SKILL.md" 2>/dev/null || echo "Could not read skill")
            
            send_with_keyboard "$(cat <<EOF
🔄 *agenticEvolve cycle complete*
📡 Signals: $SIGNALS
🛠 Skill built: \`$SKILL_NAME\`
💰 Cost today: \$$COST

\`\`\`
$SKILL_PREVIEW
\`\`\`
EOF
)" '{"inline_keyboard":[[{"text":"✅ Approve","callback_data":"approve:'"$SKILL_NAME"'"},{"text":"❌ Reject","callback_data":"reject:'"$SKILL_NAME"'"}]]}'
        fi
        ;;

    build_failed)
        SIGNALS="${2:-0}"
        COST="${5:-0}"
        send "$(cat <<EOF
⚠️ *agenticEvolve: build failed*
📡 Signals: $SIGNALS
❌ Skill builder could not complete
💰 Cost today: \$$COST
Check: \`ae log\`
EOF
)"
        ;;

    gc_complete)
        send "🧹 *agenticEvolve: weekly cleanup complete*
Check: \`ae log\`"
        ;;

    *)
        # Raw message
        [ -n "$TYPE" ] && send "$TYPE"
        ;;
esac
