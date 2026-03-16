# Commands

39 Telegram commands + 32 CLI REPL commands. Regular text messages are routed to Claude Code as chat with full session continuity. Most commands work in both Telegram and the CLI TUI (`ae`).

## Core

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Full command list |
| `/status` | System overview (gateway, memory, sessions, cost, autonomy) |
| `/heartbeat` | Liveness check |
| `/config` | View runtime config |

## Memory & Sessions

| Command | Description |
|---------|-------------|
| `/memory` | Show bounded memory (MEMORY.md + USER.md) |
| `/soul` | View agent personality (SOUL.md) |
| `/sessions [--limit N]` | List recent sessions |
| `/search <query> [--limit N]` | FTS5 full-text search across all past sessions |
| `/newsession [title]` | Force start a new session |

## Model & Cost

| Command | Description |
|---------|-------------|
| `/model [name]` | View or switch model (sonnet/opus/haiku) |
| `/cost [--week]` | Cost breakdown (today or this week) |
| `/autonomy [level]` | View or change autonomy level |

## Pipelines

| Command | Description |
|---------|-------------|
| `/evolve [--dry-run]` | Run signal → skill pipeline (includes RETRO before BUILD) |
| `/absorb <target> [--dry-run]` | Deep scan → self-improve |
| `/learn <target>` | Deep-dive a repo or tech |
| `/learnings [query] [--limit N]` | Search past findings |
| `/do <instruction> [--preview]` | Natural language → command parser |

## Skills & Queue

| Command | Description |
|---------|-------------|
| `/skills` | List installed Claude Code skills |
| `/queue` | Show skills pending approval |
| `/approve <name> [--force]` | Install a queued skill |
| `/reject <name> [reason]` | Remove a queued skill |

## Cron & Scheduling

| Command | Description |
|---------|-------------|
| `/loop <interval> <prompt>` | Create a recurring cron job |
| `/loops` | List active loops |
| `/unloop <id>` | Cancel a loop |
| `/pause <id> [--all]` | Pause a cron job |
| `/unpause <id> [--all]` | Resume a paused job |
| `/notify <delay> <msg>` | Set a one-shot reminder |

## Maintenance

| Command | Description |
|---------|-------------|
| `/gc [--dry-run]` | Run garbage collection |
| `/scanskills` | AgentShield security scan of all installed skills |

## Signals & Digests

| Command | Description |
|---------|-------------|
| `/evolve [--dry-run]` | Scan 12 signal sources, build and auto-install skills |
| `/produce [--ideas N]` | Brainstorm business ideas from trending signals |
| `/reflect [--days N]` | Self-analysis: patterns, avoidance, next actions |
| `/digest [--days N]` | Morning briefing (sessions, signals, cost) |
| `/wechat [--hours N]` | WeChat group chat digest (reads local decrypted DBs) |
| `/discord [--hours N]` | Discord channel digest (from Chromium cache + stored messages) |
| `/whatsapp [--hours N]` | WhatsApp group digest (from stored messages) |

## Subscribe & Serve

| Command | Description |
|---------|-------------|
| `/subscribe` | Browsable modal to select channels/groups to monitor for digests. Sources: DB subscriptions, platform_messages, WhatsApp auth, Discord Chromium cache |
| `/serve` | Select channels/contacts where the agent actively responds. Discord serve currently disabled (account limited) |

## Utilities (Telegram + TUI)

| Command | Description |
|---------|-------------|
| `/speak <text>` | Text-to-speech (edge-tts, auto-detects language) |
| `/do <instruction> [--preview]` | Natural language → structured command parser |
| `/lang [code]` | Set persistent output language (zh, ja, ko, es, fr, de, ru, etc.). Works across all platforms |
| `/restart` | Restart gateway remotely |
