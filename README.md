# agenticEvolve

A personal closed-loop agentic system that evolves your development capabilities daily.

Built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) as the agent engine — zero custom agent loops. Intelligence lives in prompts, memory, and skills.

```
┌────────────────────────────────────────────────────────────────┐
│                      agenticEvolve v2                          │
│                                                                │
│  ┌────────────┐  ┌────────────────┐  ┌──────────────────┐     │
│  │  Gateway    │  │  Claude Code   │  │  Memory System   │     │
│  │  (Python)   │→ │  (claude -p)   │→ │  MEMORY.md       │     │
│  │            │  │  + skills (7)  │  │  USER.md         │     │
│  │  Telegram  │  │  + MCP         │  │  SQLite+FTS5     │     │
│  │  Discord   │  │  + subagents   │  │  Learnings DB    │     │
│  │  WhatsApp  │  └────────────────┘  └──────────────────┘     │
│  │  CLI       │         ↑                     ↑                │
│  └────────────┘         │                     │                │
│         ↑          ┌────┴────┐         ┌──────┴─────┐         │
│         │          │  Cron   │         │ Session DB │         │
│         │          │Scheduler│         │  (FTS5)    │         │
│    ┌────┴────┐     └─────────┘         └────────────┘         │
│    │Pipelines│                                                 │
│    │ evolve  │  ┌───────────────────────────────────────┐     │
│    │ absorb  │  │       SOUL.md + AGENTS.md             │     │
│    │ learn   │  │    (personality + project context)     │     │
│    │ gc      │  └───────────────────────────────────────┘     │
│    └─────────┘                                                 │
└────────────────────────────────────────────────────────────────┘
```

## What it does

- **Bidirectional messaging** — talk to it from Telegram, Discord, or WhatsApp with full Claude Code capabilities (file ops, terminal, web search, MCP, skills)
- **Persistent memory** — bounded memory (MEMORY.md + USER.md) and SQLite+FTS5 session/learnings database. Injected into every call, searchable across all past conversations
- **Self-evolving** — scans GitHub trending, Hacker News, and X for developer signals, then auto-builds Claude Code skills (with human approval gate)
- **Absorbs from the wild** — deep-scans any repo/URL/topic, compares against itself, identifies gaps, and implements improvements to its own codebase
- **Learns and remembers** — extracts patterns from repos and tools, stores structured findings with verdicts (ADOPT/STEAL/SKIP) in a searchable learnings DB
- **Security-first** — automated security scanner checks all external repos for credential exfiltration, reverse shells, malicious install hooks, obfuscated payloads, and macOS persistence before any code touches the system
- **Natural language commands** — `/do absorb this repo and skip the security scan` gets parsed into `/absorb <url> --skip-security-scan` and runs in background with 1-minute progress reports
- **Cost-controlled** — daily/weekly caps enforced before every Claude invocation

## Pipelines

### `/evolve` — Signal → Skill

5-stage pipeline: **COLLECT → ANALYZE → BUILD → REVIEW → REPORT**

1. Signal collectors scan GitHub trending, HN, and X
2. Analyzer scores signals on relevance, novelty, actionability (0-9)
3. Builder creates skills using [skill-creator quality standards](#skills) for candidates scoring ≥ 7.0
4. Reviewer agent validates security, quality, correctness
5. Skills land in `skills-queue/` — requires human `/approve` to install

Supports `--dry-run` (stops after ANALYZE, shows what would be built) and `--skip-security-scan`.

### `/absorb <target>` — Deep Scan → Self-Improve

5-stage pipeline: **SCAN → GAP → PLAN → IMPLEMENT → REPORT**

1. Deep-scans target (clones repos, reads source, maps architecture)
2. Gap analysis compares target against our system
3. Planner creates concrete file-level implementation plan
4. Implementer modifies our system files to absorb improvements
5. Changes logged in learnings DB

Supports `--dry-run` (stops after GAP, shows gaps by priority) and `--skip-security-scan`.

### `/learn <target>` — Pattern Extraction

Deep-dives a repo, URL, or technology. Extracts patterns for operational benefit — not book reports. Returns structured findings with three verdicts:

- **ADOPT** — use it directly
- **STEAL** — take the patterns, skip the dependency
- **SKIP** — not useful for our workflow

Findings persist in SQLite+FTS5, searchable via `/learnings`. Supports `--skip-security-scan`.

### `/do <instruction>` — Natural Language Command

Parses free-text instructions into structured commands using a lightweight Claude Haiku call, then executes them in background with 1-minute progress reports.

```
/do absorb this repo https://github.com/foo/bar and skip the security scan
→ Parsed: /absorb https://github.com/foo/bar --skip-security-scan (confidence: 95%)
→ Running...
→ [/absorb ...] Still running... (60s elapsed, ~1 min)
→ [/absorb ...] Completed in 245s.
```

Maps synonyms naturally: "study"/"research" → `/learn`, "integrate"/"steal from" → `/absorb`, "find new tools" → `/evolve`, "preview"/"just check" → `--dry-run`, "skip security"/"no scan" → `--skip-security-scan`.

### Security Scanner

All pipelines (`/absorb`, `/learn`, `/evolve`) run an automated security scan on external repos before processing. The scanner checks for:

| Threat | Examples |
|--------|----------|
| Credential exfiltration | Reading `~/.ssh`, `~/.aws`, macOS Keychain dumps |
| Reverse shells | Bash/netcat/Python reverse shells |
| Remote code execution | `curl \| bash`, download-and-execute patterns |
| Obfuscated payloads | Base64-encoded shell commands, hex payloads |
| Malicious install hooks | npm `postinstall`, Python `setup.py` cmdclass |
| Destructive commands | `rm -rf /`, fork bombs, disk wipes |
| Crypto miners | xmrig, stratum connections |
| macOS persistence | LaunchAgents, login items, TCC resets |

**Verdicts:**
- **BLOCKED** — critical threat detected, pipeline aborted
- **WARNING** — suspicious patterns found, proceeds with caution
- **SAFE** — no threats detected

Use `--skip-security-scan` to bypass (when you trust the source).

### `/gc` — Garbage Collection

Cleans stale sessions (30d), empty sessions (24h), orphan skills (7d), checks memory entropy (85% threshold), rotates logs. Supports `--dry` preview mode.

## Telegram Commands (28)

| Command | Description |
|---------|-------------|
| `/start`, `/help` | Welcome message, command list |
| `/status` | System overview (gateway, memory, sessions, cost) |
| `/heartbeat` | Liveness check |
| `/config` | View runtime config (model, caps, platforms) |
| `/memory` | Show bounded memory (MEMORY.md + USER.md) |
| `/soul` | View agent personality (SOUL.md) |
| `/sessions` | List recent sessions |
| `/search <query>` | FTS5 full-text search across past sessions |
| `/newsession` | Force start a new session |
| `/cost` | Today's cost breakdown |
| `/model [name]` | View or switch model (sonnet/opus/haiku) |
| `/evolve` | Run signal → skill pipeline |
| `/absorb <target>` | Deep scan → self-improve pipeline |
| `/learn <target>` | Deep-dive a repo or tech |
| `/learnings [query]` | Search past /learn findings |
| `/skills` | List installed Claude Code skills |
| `/loop` | Create a recurring cron job |
| `/loops` | List active loops |
| `/unloop <id>` | Cancel a loop |
| `/pause <id>` | Pause a cron job |
| `/unpause <id>` | Resume a paused cron job |
| `/notify` | Set a one-shot reminder |
| `/queue` | Show skills pending approval |
| `/approve <name>` | Install a queued skill |
| `/reject <name>` | Remove a queued skill |
| `/gc` | Run garbage collection |
| `/do <instruction>` | Natural language → command parser |

Regular text messages are routed to Claude Code as chat with full session continuity.

## How it works

Each incoming message:

1. **Gateway** receives message from Telegram/Discord/WhatsApp
2. **Session manager** resolves or creates a session (idle timeout = 2h)
3. **Cost cap** is checked before invoking Claude (daily + weekly)
4. **Conversation history** from the current session is loaded (last 20 turns, 8K chars)
5. **System prompt** is assembled from SOUL.md + MEMORY.md + USER.md
6. **Claude Code** (`claude -p`) processes the message with full tool access
7. **Streaming progress** — tool use events are batched and sent as typing indicators
8. **Response** is sent back to the platform
9. **Message + response** are persisted to SQLite for future search

The cron scheduler runs inside the gateway process, ticking every 60 seconds to execute due jobs and deliver results to your platform. Supports standard 5-field cron expressions (`0 6 * * *`) with timezone awareness.

## Skills (7 installed)

Skills follow the [official skill-creator](https://github.com/anthropics/claude-plugins-official) quality standards — short imperative descriptions with "ALWAYS read this skill" framing, progressive disclosure, and proper frontmatter.

| Skill | Purpose | Trigger |
|-------|---------|---------|
| **session-search** | FTS5 search across past conversations | "we talked about...", "remember when..." |
| **cron-manager** | Schedule recurring agent tasks | "cron", "schedule", "recurring job", "run every" |
| **brave-search** | Web search via Brave API | "search for", "look up", "what's the latest on" |
| **skill-creator** | Create, eval, benchmark, and optimize skills | "create a skill", "optimize this skill" |
| **nah** | PreToolUse permission guard | Explicit invocation only |
| **agent-browser-protocol** | Chromium browser automation MCP | Explicit invocation only |
| **unf** | Auto file versioning daemon | Explicit invocation only |

Skills with `disable-model-invocation: true` (nah, ABP, unf, cron-manager) only trigger when explicitly invoked — they're install/config tools, not general-purpose.

## Project structure

```
~/.agenticEvolve/
├── ae                          # CLI entrypoint
├── config.yaml                 # Settings (model, platforms, cost caps)
├── .env                        # Secrets (bot tokens)
├── SOUL.md                     # Agent personality
├── AGENTS.md                   # Project conventions + agent roles
│
├── gateway/                    # Messaging gateway (~4,500 lines Python)
│   ├── run.py                  # GatewayRunner — main process
│   ├── agent.py                # Claude Code invocation wrapper
│   ├── evolve.py               # 5-stage evolve pipeline
│   ├── absorb.py               # 5-stage absorb pipeline
│   ├── security.py             # Security scanner (credential theft, reverse shells, etc.)
│   ├── gc.py                   # Garbage collection
│   ├── config.py               # Config loader (YAML + .env)
│   ├── session_db.py           # SQLite + FTS5 (sessions + learnings)
│   └── platforms/
│       ├── base.py             # Platform adapter interface
│       ├── telegram.py         # Telegram (~2,000 lines, 28 commands)
│       ├── discord.py          # Discord (written, untested)
│       └── whatsapp.py         # WhatsApp (written, untested)
│
├── memory/
│   ├── MEMORY.md               # Agent's notes (2200 char limit)
│   ├── USER.md                 # User profile (1375 char limit)
│   └── sessions.db             # SQLite + FTS5
│
├── cron/
│   └── jobs.json               # Scheduled jobs
│
├── skills-queue/               # Skills pending human approval
│
├── collectors/                 # Signal collectors (bash)
│   ├── github.sh
│   ├── hackernews.sh
│   └── x-search.sh
│
├── whatsapp-bridge/            # Node.js WhatsApp bridge
│   └── bridge.js
│
└── logs/
    ├── gateway.log
    └── cost.log

~/.claude/skills/               # Installed Claude Code skills
├── memory/
├── session-search/
├── cron-manager/
├── brave-search/
├── skill-creator/              # Official skill-creator (create, eval, benchmark, optimize)
│   ├── SKILL.md
│   ├── agents/                 # Grader, Comparator, Analyzer subagents
│   ├── scripts/                # run_eval.py, run_loop.py, aggregate_benchmark.py
│   ├── eval-viewer/            # HTML viewer for qualitative + quantitative review
│   ├── references/             # JSON schemas
│   └── assets/                 # Templates
├── nah/
├── agent-browser-protocol/
└── unf/
```

## Setup

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (`npm install -g @anthropic-ai/claude-code`) — authenticated
- Python 3.11+
- (Optional) Node.js 18+ — only for WhatsApp
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

### Gateway

```bash
ae gateway              # Start the messaging gateway
ae gateway stop         # Stop it
ae gateway status       # Check if running
ae gateway install      # Install as launchd service (auto-start on boot)
```

### Memory

```bash
ae memory               # Show bounded memory state
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
ae status               # System overview
ae cost                 # Cost breakdown
ae doctor               # Diagnose issues
```

## Key design decisions

- **Claude Code is the agent engine** — no custom agent loop, no tool registry. `claude -p` has 25+ tools, MCP, skills, and subagent delegation. We build infrastructure around it, not a competing agent.
- **Bounded memory** — MEMORY.md (2200 chars) + USER.md (1375 chars) with frozen snapshot pattern. Injected at session start, never changes mid-session.
- **Session continuity** — conversation history fed back into each `claude -p` call within a session (last 20 turns, 8K chars). Sessions auto-expire after 2h idle.
- **Skills follow skill-creator standards** — descriptions are "pushy" with "Use when..." clauses to avoid undertriggering. Progressive disclosure keeps SKILL.md lean, heavy docs go in references/.
- **Safety gates everywhere** — automated security scanner on all external code, skills queue with human approval, daily + weekly cost caps, user whitelisting, review agent validation, bounded memory limits.
- **Cron inside the gateway** — no OS cron dependency. Supports standard 5-field cron expressions with timezone awareness (Asia/Hong_Kong, US/Eastern, etc.), interval-based, and one-shot jobs. Pause/unpause via Telegram.

## Platform support

| Platform | Status | Library |
|----------|--------|---------|
| Telegram | Working (28 commands) | python-telegram-bot |
| Discord | Written, untested | discord.py |
| WhatsApp | Written, untested | @whiskeysockets/baileys (Node.js bridge) |

## Inspiration

- [hermes-agent](https://github.com/NousResearch/hermes-agent) — bounded memory, session persistence, messaging gateway, agent-managed cron
- [Anthropic skill-creator](https://github.com/anthropics/claude-plugins-official) — skill creation patterns, eval-driven development, description optimization
- [snarktank/ralph](https://github.com/snarktank/ralph) — v1 inspiration (bash orchestrator, two-tier learning)

## License

MIT
