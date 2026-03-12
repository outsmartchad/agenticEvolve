# agenticEvolve

A personal AI agent that lives on your messaging platforms, remembers you across sessions, scans for developer signals, and evolves your capabilities daily.

Built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) as the agent engine — zero custom agent code. The intelligence lives in prompts, memory, and skills.

```
┌──────────────────────────────────────────────────────────────┐
│                     agenticEvolve v2                          │
│                                                              │
│  ┌────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  Gateway    │  │  Claude Code   │  │  Memory System   │   │
│  │  (Python)   │→ │  (claude -p)   │→ │  MEMORY.md       │   │
│  │            │  │  with tools    │  │  USER.md         │   │
│  │  Telegram  │  │  + skills      │  │  SQLite+FTS5     │   │
│  │  Discord   │  │  + MCP         │  │                  │   │
│  │  WhatsApp  │  └────────────────┘  └──────────────────┘   │
│  │  CLI       │         ↑                     ↑              │
│  └────────────┘         │                     │              │
│         ↑               │              ┌──────┴─────┐       │
│         │          ┌────┴────┐         │ Session DB │       │
│         │          │  Cron   │         │ (FTS5)     │       │
│         │          │Scheduler│         └────────────┘       │
│         │          └─────────┘                               │
│  ┌──────┴───────────────────────────────────────────┐       │
│  │              SOUL.md + AGENTS.md                  │       │
│  │         (personality + project context)           │       │
│  └───────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

## What it does

- **Talk to it from Telegram, Discord, or WhatsApp** — bidirectional messaging with full Claude Code capabilities (file ops, terminal, web search, MCP, skills)
- **Remembers you across sessions** — bounded memory (MEMORY.md + USER.md) injected into every call, conversation history within sessions
- **Scans for developer signals** — GitHub trending, Hacker News, X/Twitter via scheduled cron jobs
- **Auto-creates skills** — when it solves a complex problem, it can save the workflow as a reusable Claude Code skill
- **Cost-controlled** — daily/weekly caps with automatic enforcement

## How it works

Each incoming message:

1. **Gateway** receives message from Telegram/Discord/WhatsApp
2. **Session manager** resolves or creates a session (idle timeout = 2h)
3. **Cost cap** is checked before invoking Claude
4. **Conversation history** from the current session is loaded and injected
5. **System prompt** is assembled from SOUL.md + MEMORY.md + USER.md
6. **Claude Code** (`claude -p`) processes the message with full tool access
7. **Response** is sent back to the platform
8. **Message + response** are persisted to SQLite for future search

The cron scheduler runs inside the gateway process, ticking every 60 seconds to execute due jobs and deliver results to your platform.

## Project structure

```
~/.agenticEvolve/
├── ae                       # CLI entrypoint
├── config.yaml              # Settings (model, platforms, cost caps)
├── .env                     # Secrets (bot tokens)
├── SOUL.md                  # Agent personality
│
├── gateway/                 # Messaging gateway (Python)
│   ├── run.py               # GatewayRunner — main process
│   ├── agent.py             # Claude Code invocation wrapper
│   ├── config.py            # Config loader (YAML + .env)
│   ├── session_db.py        # SQLite + FTS5 session persistence
│   └── platforms/
│       ├── base.py          # Platform adapter interface
│       ├── telegram.py      # Telegram (python-telegram-bot)
│       ├── discord.py       # Discord (discord.py)
│       └── whatsapp.py      # WhatsApp (Baileys Node.js bridge)
│
├── memory/
│   ├── MEMORY.md            # Agent's notes (2200 char limit)
│   ├── USER.md              # User profile (1375 char limit)
│   └── sessions.db          # SQLite + FTS5
│
├── cron/
│   ├── jobs.json            # Scheduled jobs
│   └── output/              # Job output history
│
├── whatsapp-bridge/         # Node.js WhatsApp bridge
│   ├── bridge.js            # Baileys subprocess (JSON stdin/stdout)
│   └── package.json
│
├── collectors/              # Signal collectors (bash)
│   ├── github.sh
│   ├── hackernews.sh
│   └── x-search.sh
│
├── skills/                  # Claude Code skill definitions
│   ├── memory/SKILL.md      # Memory management (/memory add|replace|remove)
│   ├── session-search/SKILL.md  # FTS5 session search
│   └── cron-manager/SKILL.md    # Job scheduling
│
└── logs/
    ├── gateway.log
    └── cost.log
```

## Setup

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (`npm install -g @anthropic-ai/claude-code`) — authenticated
- Python 3.11+
- (Optional) Node.js 18+ — only needed for WhatsApp
- (Optional) [GitHub CLI](https://cli.github.com/) — for signal collectors

### Install

```bash
# Clone
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve

# Symlink the CLI
mkdir -p ~/.local/bin
ln -sf ~/.agenticEvolve/ae ~/.local/bin/ae

# Install Python dependencies
pip install -r ~/.agenticEvolve/requirements.txt

# First-time setup
ae setup
```

### Configure

```bash
# Create .env from template
cp ~/.agenticEvolve/.env.example ~/.agenticEvolve/.env

# Add your bot token(s)
vim ~/.agenticEvolve/.env
```

At minimum, set one platform token:

```bash
# Telegram (get from @BotFather)
TELEGRAM_BOT_TOKEN=your-token-here
```

Then add your Telegram user ID to `config.yaml`:

```yaml
platforms:
  telegram:
    allowed_users: [your-user-id]
```

To find your user ID, start the bot and send any message — it will reply with your ID.

## Usage

### Gateway (primary)

```bash
ae gateway              # Start the messaging gateway
ae gateway stop         # Stop it
ae gateway status       # Check if running
ae gateway install      # Install as launchd service (auto-start on boot)
```

### Memory

```bash
ae memory               # Show bounded memory state (MEMORY.md + USER.md)
ae memory reset         # Clear all memory
```

### Sessions

```bash
ae sessions list        # Browse past sessions
ae sessions search Q    # Full-text search across all conversations
ae sessions stats       # Session statistics
```

### Status & Cost

```bash
ae status               # System overview (gateway, memory, sessions, cost)
ae cost                 # Cost breakdown
ae doctor               # Diagnose issues
```

### Config

```bash
ae config               # Show config.yaml
ae config edit          # Open in editor
ae setup                # First-time setup wizard
```

### Legacy (v1)

```bash
ae cycle                # Run one signal scan cycle
ae collect [source]     # Run collectors (github, hackernews, x-search)
```

## Key design decisions

- **Claude Code is the agent engine** — no custom agent loop, no tool registry. Claude Code already has 25+ tools, MCP, skills, and subagent delegation. We build infrastructure around `claude -p`, not a competing agent.
- **Bounded memory** — MEMORY.md (2200 chars) + USER.md (1375 chars) with frozen snapshot pattern. Injected at session start, never changes mid-session. Managed via a Claude Code skill.
- **Session continuity** — conversation history is fed back into each `claude -p` call within a session (last 20 turns, 8K chars max). Sessions auto-expire after 2h idle.
- **User verification** — Telegram users must be whitelisted by user ID. Unknown users get a message with their ID to send to the bot owner.
- **Cost caps** — $5/day, $25/week (configurable). Enforced before every Claude invocation.
- **Cron inside the gateway** — no OS cron dependency. Jobs run in fresh sessions with self-contained prompts.

## Platform support

| Platform | Status | Library |
|----------|--------|---------|
| Telegram | Working | python-telegram-bot |
| Discord | Written, untested | discord.py |
| WhatsApp | Written, untested | @whiskeysockets/baileys (Node.js subprocess) |

## Skills

Skills are Claude Code's native extensibility mechanism. agenticEvolve ships with 3 built-in skills:

| Skill | Command | Purpose |
|-------|---------|---------|
| memory | `/memory add\|replace\|remove` | Manage persistent bounded memory |
| session-search | `/session-search <query>` | FTS5 search across past conversations |
| cron-manager | `/cron add\|list\|remove` | Schedule recurring agent tasks |

Skills auto-install to `~/.claude/skills/` and are available in all Claude Code sessions.

## Inspiration

- [hermes-agent](https://github.com/NousResearch/hermes-agent) — bounded memory, session persistence, messaging gateway, agent-managed cron
- [snarktank/ralph](https://github.com/snarktank/ralph) — v1 inspiration (bash orchestrator, two-tier learning)
- [Anthropic's harness engineering research](https://www.anthropic.com/) — initializer agent pattern

## License

MIT
