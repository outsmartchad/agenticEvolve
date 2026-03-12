#!/bin/bash
# Discord signal collector — reads recent messages from configured channels via REST API
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"

if [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
    echo "DISCORD_BOT_TOKEN not set. Skipping Discord collection."
    exit 0
fi

if [ -z "${DISCORD_CHANNELS:-}" ]; then
    echo "DISCORD_CHANNELS not set. Skipping Discord collection."
    echo "Set DISCORD_CHANNELS as space-separated 'channel_id:label' pairs in .env"
    exit 0
fi

TODAY=$(date +%Y-%m-%d)
OUTDIR="$SIGNALS/$TODAY"
mkdir -p "$OUTDIR"

echo "Collecting Discord signals..."
> "$OUTDIR/discord.json"

for channel_entry in $DISCORD_CHANNELS; do
    CHANNEL_ID="${channel_entry%%:*}"
    LABEL="${channel_entry##*:}"

    # Fetch last 25 messages from this channel
    curl -sL "https://discord.com/api/v10/channels/${CHANNEL_ID}/messages?limit=25" \
        -H "Authorization: Bot ${DISCORD_BOT_TOKEN}" \
        | jq --arg label "$LABEL" --arg today "$TODAY" '
            .[] | select(
                (.timestamp | split("T")[0]) == $today
                and (.content | length) > 20
            ) | {
                id: ("discord-" + .id),
                source: "discord",
                timestamp: .timestamp,
                author: .author.username,
                title: ("#" + $label + ": " + (.content | .[0:80])),
                content: .content,
                url: ("https://discord.com/channels/@me/" + .channel_id + "/" + .id),
                metadata: {
                    channel: $label,
                    reactions: ([.reactions[]?.count] | add // 0),
                    relevance_tags: ["discord", $label]
                }
            }
        ' >> "$OUTDIR/discord.json" 2>/dev/null || true

    sleep 0.3  # Discord rate limit: 50 req/s globally per bot
done

TOTAL=$(cat "$OUTDIR/discord.json" 2>/dev/null | jq -s 'length')
echo "Discord: $TOTAL signals collected"
