# Telegram Commands

29 commands available. Regular text messages are routed to Claude Code as chat with full session continuity.

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
| `/evolve [--dry-run]` | Run signal → skill pipeline |
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
