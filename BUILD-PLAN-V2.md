# Build Plan v2: Personal Agent That Grows With You

> Author: Vincent So (@outsmartchad)
> Date: 2026-03-12
> Engine: Claude Code (not a custom agent loop — we build on top of Anthropic's agent)
> Inspiration: hermes-agent (NousResearch), ralph (snarktank), v1 agenticEvolve

---

## Why v2

v1 was a batch cron job: collect signals → run LLM → output file → sleep. It had no interactivity, no memory that grows with use, no way to learn from conversations, and no way to help during your workday.

v2 is a **persistent personal agent** that:
- Lives on Telegram, Discord, and WhatsApp — talk to it from your phone
- Remembers you across sessions (bounded memory + user profile + session search)
- Creates skills when it solves hard problems (not just from scanning HN)
- Runs scheduled automations with results delivered to any platform
- Still scans GitHub/HN/X for signals, but as one capability among many

---

## Architecture Overview

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
│         │               │                                    │
│  ┌──────┴───────────────┴──────────────────────────┐        │
│  │              SOUL.md + AGENTS.md                 │        │
│  │         (personality + project context)          │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

### How Claude Code fits in

Claude Code is the **agent engine**. We don't build our own tool-calling loop.

- `claude -p "<prompt>" --model sonnet --dangerously-skip-permissions` is our agent invocation
- Claude Code already has: terminal, file ops, web search/fetch, glob, grep, read, edit, write, MCP, skills, subagent delegation
- We build **around** it: gateway routes messages to `claude -p`, memory persists across calls, cron schedules calls, session DB enables recall

Each gateway message becomes a `claude -p` call with:
1. A system prompt assembled from SOUL.md + MEMORY.md + USER.md + session context
2. The user's message
3. `--append-system-prompt` to inject memory and personality
4. Response streamed back to the platform

---

## Component Design

### 1. Memory System

Directly inspired by hermes-agent. Two bounded markdown files + a memory management Claude Code skill.

```
~/.agenticEvolve/memory/
├── MEMORY.md        # Agent's notes (2200 char limit, ~800 tokens)
├── USER.md          # User profile (1375 char limit, ~500 tokens)
└── sessions.db      # SQLite with FTS5 for session search
```

**MEMORY.md** — agent's personal notes:
- Environment facts, project conventions, tool quirks
- Lessons learned, completed work diary
- Managed via a Claude Code skill: `/memory add|replace|remove`

**USER.md** — user profile:
- Name, role, timezone, communication preferences
- Technical skill level, pet peeves
- Managed via same skill: `/memory add|replace|remove --target user`

**Key design decisions (from hermes-agent):**
- **Frozen snapshot pattern**: Memory is injected into system prompt at session start, never changes mid-session. Changes persist to disk immediately but only appear in next session. This preserves LLM prefix cache.
- **Character limits**: When full, agent must consolidate/replace before adding. System prompt header shows capacity (`67% — 1,474/2,200 chars`).
- **Security scanning**: Memory entries are scanned for injection patterns before acceptance.
- **Duplicate prevention**: Exact duplicates are silently rejected.

**Implementation**: A Claude Code skill at `~/.claude/skills/memory/SKILL.md` that:
- Reads/writes `~/.agenticEvolve/memory/MEMORY.md` and `USER.md`
- Enforces character limits
- Supports add/replace (substring match)/remove operations
- Returns current state after each operation

### 2. Session Persistence

```python
# sessions.db schema
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,          -- YYYYMMDD_HHMMSS_hex
    source TEXT NOT NULL,         -- "cli", "telegram", "discord", "whatsapp"
    user_id TEXT,
    title TEXT,                   -- human-readable, unique
    model TEXT,
    started_at TEXT,
    ended_at TEXT,
    message_count INTEGER DEFAULT 0,
    token_count_in INTEGER DEFAULT 0,
    token_count_out INTEGER DEFAULT 0
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    role TEXT NOT NULL,           -- "user", "assistant", "system", "tool"
    content TEXT,
    timestamp TEXT,
    token_count INTEGER DEFAULT 0
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);
```

**Session search** is a Claude Code skill (`/session-search`) that:
- Takes a query string
- Runs FTS5 search across all past messages
- Groups by session, returns top 3 with context
- Uses Claude to summarize relevant passages

### 3. Messaging Gateway

A long-running Python process (`ae gateway`) that:
1. Connects to Telegram, Discord, and WhatsApp
2. Routes incoming messages to Claude Code via `claude -p`
3. Streams responses back to the platform
4. Manages per-chat sessions (session key = platform:chat_id)
5. Runs the cron scheduler in a background thread

```
~/.agenticEvolve/
├── gateway/
│   ├── __init__.py
│   ├── run.py              # GatewayRunner — main event loop
│   ├── config.py           # Platform config resolution
│   ├── session.py          # Session store, context assembly
│   ├── agent.py            # Claude Code invocation wrapper
│   └── platforms/
│       ├── base.py         # BasePlatformAdapter ABC
│       ├── telegram.py     # python-telegram-bot
│       ├── discord.py      # discord.py
│       └── whatsapp.py     # Baileys bridge (Node.js subprocess)
├── cron/
│   ├── scheduler.py        # Tick-based scheduler (60s interval)
│   ├── jobs.json           # Job definitions
│   └── output/             # Job output history
```

**Session routing** (from hermes-agent):
- DMs: `agent:main:<platform>:dm` (one session per bot per platform)
- Groups: `agent:main:<platform>:group:<chat_id>` (per-group)
- WhatsApp DMs include chat_id (multi-user)

**Session reset policies**:
- `idle` — reset after N minutes of inactivity
- `daily` — reset at a specific hour
- Before reset, agent gets one turn to save memories/skills

**Agent invocation** — each incoming message becomes:
```bash
claude -p "<assembled_prompt>" \
    --model sonnet \
    --append-system-prompt "<memory + user profile + session context>" \
    --dangerously-skip-permissions \
    --output-format stream-json \
    --verbose
```

The gateway parses stream-json output, extracts text responses, and sends them back to the platform.

### 4. SOUL.md (Personality)

A markdown file that defines the agent's personality:
```
~/.agenticEvolve/SOUL.md          # Global personality
./SOUL.md                         # Per-project override (checked first)
```

Injected into system prompt with instruction:
> "If SOUL.md is present, embody its persona and tone."

Example:
```markdown
# SOUL.md

You are Vincent's personal AI agent. You are direct, technical, and concise.

## Personality
- No filler, no unnecessary praise
- Show file paths with line numbers
- When uncertain, ask one targeted question
- Default to building things, not explaining things

## Context
- Vincent is building AI agents and onchain infrastructure
- He prefers TypeScript for backends, React for frontends
- Timezone: HKT (UTC+8)
```

### 5. Agent-Managed Cron

The agent can schedule tasks via natural language. A Claude Code skill (`/cron`) that:
- Creates/lists/removes jobs in `~/.agenticEvolve/cron/jobs.json`
- Supports: relative delays (`30m`), intervals (`every 2h`), cron expressions (`0 9 * * *`)
- Each job specifies: prompt, schedule, delivery target (telegram, discord, whatsapp, local)

The gateway's scheduler thread ticks every 60s:
1. Load jobs.json
2. Check each job's `next_run_at`
3. For due jobs: spawn `claude -p` with the job's prompt
4. Deliver output to the target platform
5. Update run count, compute next run time

**Self-contained prompts** (from hermes-agent): Cron prompts run in fresh sessions. They must include all context — no "check on that thing."

### 6. Signal Collectors (v1 retained)

The v1 collectors (GitHub, HN, X) become **cron jobs** managed by the agent:
```
"Every 2 hours, collect signals from GitHub trending, HN, and X/Twitter.
Analyze for useful developer tools. If something is actionable, create
a Claude Code skill for it in ~/.claude/skills/."
```

This replaces the rigid v1 pipeline with a flexible, agent-driven approach.

### 7. Skills That Emerge From Use

Beyond signal scanning, the agent should create skills when:
- It completes a complex task (5+ tool calls) successfully
- It hit errors and found the working path
- The user corrected its approach
- It discovered a non-trivial workflow

This is handled by a **system prompt instruction** (not code):
> "After completing a complex task, evaluate if the workflow should be saved as a reusable skill. If so, create it in ~/.claude/skills/ using the Write tool."

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent engine | Claude Code (`claude -p`) | Already has 25+ tools, MCP, skills. No need to rebuild. |
| Gateway | Python 3.11+ | asyncio for concurrent platform connections |
| Telegram | `python-telegram-bot` | Most mature Python Telegram library |
| Discord | `discord.py` | Standard Discord library |
| WhatsApp | Baileys (Node.js subprocess) | Only reliable WhatsApp library. Hermes-agent uses same approach. |
| Session DB | SQLite + FTS5 | Zero-dependency, fast full-text search |
| Cron | Built-in scheduler (no OS cron) | Agent-managed, platform-aware delivery |
| Config | YAML (`config.yaml`) + `.env` | Secrets in .env, everything else in YAML |

---

## Directory Structure (v2)

```
~/.agenticEvolve/
├── config.yaml              # All settings (model, platforms, memory limits, etc.)
├── .env                     # API keys and secrets (Telegram, Discord tokens, etc.)
├── SOUL.md                  # Global personality
│
├── gateway/                 # Messaging gateway (Python package)
│   ├── __init__.py
│   ├── run.py               # GatewayRunner — main process
│   ├── config.py            # Config resolution
│   ├── session.py           # Session management
│   ├── agent.py             # Claude Code wrapper
│   └── platforms/
│       ├── base.py
│       ├── telegram.py
│       ├── discord.py
│       └── whatsapp.py
│
├── memory/
│   ├── MEMORY.md            # Agent's notes (2200 chars)
│   ├── USER.md              # User profile (1375 chars)
│   └── sessions.db          # SQLite + FTS5
│
├── cron/
│   ├── scheduler.py
│   ├── jobs.json
│   └── output/
│
├── collectors/              # v1 signal collectors (retained)
│   ├── github.sh
│   ├── hackernews.sh
│   └── x-search.sh
│
├── skills/                  # Claude Code skills built by the system
│   ├── memory/SKILL.md      # Memory management skill
│   ├── session-search/SKILL.md
│   ├── cron/SKILL.md
│   └── ... (auto-created)
│
├── logs/
│   ├── gateway.log
│   ├── cron.log
│   └── cost.log
│
├── whatsapp-bridge/         # Node.js WhatsApp bridge
│   ├── package.json
│   ├── bridge.js
│   └── auth/                # WhatsApp session data
│
└── ae                       # CLI entrypoint (updated for v2)
```

---

## CLI Commands (v2)

```bash
# Core
ae                          # Start interactive Claude Code session with memory/SOUL
ae gateway                  # Start the messaging gateway (long-running)
ae gateway install          # Install as systemd/launchd service

# Memory
ae memory                   # Show current memory state
ae memory reset             # Clear all memory (with confirmation)

# Sessions
ae sessions list            # Browse past sessions
ae sessions search <query>  # FTS5 search across all conversations
ae sessions export <file>   # Export to JSONL

# Cron
ae cron list                # View scheduled jobs
ae cron add <schedule> <prompt>  # Add a job
ae cron remove <job_id>     # Remove a job

# Config
ae config                   # View config
ae config edit              # Open config.yaml in editor
ae config set KEY VAL       # Set a value

# Legacy (v1 compat)
ae collect [source]         # Run signal collectors
ae status                   # System status
ae cost                     # Cost tracking

# Setup
ae setup                    # Interactive first-time setup
ae doctor                   # Diagnose issues
```

---

## Build Order

### Phase 1: Foundation (this session)
1. Memory system (MEMORY.md + USER.md + Claude Code skill)
2. SOUL.md personality system
3. Session persistence (SQLite + FTS5)
4. Updated `ae` CLI

### Phase 2: Gateway
5. Gateway core (GatewayRunner, session routing, agent wrapper)
6. Telegram adapter (bidirectional)
7. Discord adapter
8. WhatsApp adapter (Baileys bridge)

### Phase 3: Automation
9. Cron scheduler (integrated into gateway)
10. Migrate v1 collectors to cron jobs
11. Skill auto-creation from complex tasks

### Phase 4: Polish
12. `ae gateway install` (systemd/launchd)
13. `ae doctor` diagnostics
14. Session search skill
15. Cost tracking across all invocations

---

## Key Differences from hermes-agent

| Decision | hermes-agent | agenticEvolve v2 |
|----------|-------------|-------------------|
| Agent engine | Custom Python loop (run_agent.py, 2600 lines) | Claude Code (`claude -p`) — zero agent code to maintain |
| Tool system | Self-registering Python tools (38 files) | Claude Code's built-in tools + MCP + skills |
| Provider | Any OpenAI-compatible API | Claude only (Anthropic subscription) — simpler, better tools |
| Skills format | Custom SKILL.md with metadata | Claude Code's native SKILL.md format |
| Memory | In-process Python tool | Claude Code skill (SKILL.md that reads/writes files) |
| Gateway | Fully integrated into agent process | Separate process that invokes `claude -p` per message |
| Install | pip install + 50 dependencies | Minimal Python (gateway only) + Claude Code |

The trade-off: we get a **much simpler codebase** (no 2600-line agent loop, no 38 tool files, no provider abstraction) at the cost of being locked to Claude. Since Claude Code is the best coding agent available and we're already paying for it, this is a good trade.
