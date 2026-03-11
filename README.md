# agenticEvolve

A personal closed-loop agentic system that ingests signals from developer platforms, analyzes them for useful tools and patterns, auto-builds [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills from discoveries, and evolves your development capabilities daily.

The harness is dumb (~150 lines of bash). The intelligence lives in the LLM prompts.

```
┌─────────────────────────────────────────────────────────────────┐
│                        OUTER LOOP (cron)                        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Signal       │  │  Analyzer    │  │  Skill       │         │
│  │  Collectors   │→ │  Agent       │→ │  Builder     │         │
│  │  (bash/curl)  │  │  (claude -p) │  │  (claude -p) │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         ↑                                    ↓                  │
│         │            ┌──────────────┐  ┌──────────────┐        │
│         └────────────│  Memory      │←─│  Reviewer    │        │
│                      │  (4 files)   │  │  (claude -p) │        │
│                      └──────────────┘  └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

## How it works

Each cycle (every 2 hours via cron):

1. **Collect** — bash scripts pull signals from GitHub, Hacker News, and X/Twitter
2. **Analyze** — a fresh `claude -p` call reads signals, picks the single most actionable item
3. **Build** — a fresh `claude -p` call builds one Claude Code skill from the top action item
4. **Review** — a fresh `claude -p` call (read-only) validates security, quality, and correctness
5. **Notify** — Telegram message with approve/reject buttons

Every stage is a **stateless Claude invocation**. No session continuity. If one cycle goes off-rails, the next starts clean.

## Key design decisions

- **One task per cycle** — prevents scope creep
- **Fresh context each cycle** — no `--resume`, no session continuity
- **Two-tier memory** — `state.md` (curated, read first) + `log.md` (raw, append-only)
- **Three gates for skills** — auto-reviewer agent, queue, human review
- **Cost caps** — $5/day, $25/week (configurable)

## Project structure

```
.
├── ae                      # CLI entrypoint (single command for humans and agents)
├── config.sh               # Configuration (cost caps, API keys, directories)
├── run-cycle.sh            # Main cycle orchestrator (~150 lines)
├── run-gc.sh               # Weekly garbage collection
├── notify.sh               # Telegram notifications with inline keyboard
├── telegram-listener.sh    # Polls for approve/reject button callbacks
├── collectors/
│   ├── github.sh           # Trending repos, starred activity, releases (via gh CLI)
│   ├── hackernews.sh       # Keyword search + Show HN (via Algolia API)
│   └── x-search.sh         # X/Twitter signals (via Brave Search API)
├── prompts/
│   ├── initialize.md       # One-time setup agent
│   ├── analyze.md          # Signal analysis agent
│   ├── build-skill.md      # Skill builder agent
│   ├── review-skill.md     # Skill reviewer agent (read-only)
│   └── gc.md               # Garbage collection agent
├── memory/
│   ├── state.md            # Curated knowledge (read first every cycle)
│   ├── log.md              # Append-only raw log
│   ├── action-items.md     # Task tracking with checkbox format
│   └── watchlist.md        # Accounts, keywords, and filters to monitor
├── signals/                # Raw collected signals (JSON per day, gitignored)
├── skills-queue/           # Skills pending human review (gitignored)
├── logs/                   # Cycle logs + cost.log (gitignored)
├── BUILD-PLAN.md           # Full architecture and design decisions
└── VISION.md               # Original vision and reference projects
```

## Setup

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (`npm install -g @anthropic-ai/claude-code`)
- [GitHub CLI](https://cli.github.com/) (`gh`) — authenticated
- `jq` and `curl`
- (Optional) Brave Search API key for X/Twitter signals
- (Optional) Telegram bot for notifications

### Install

```bash
# Clone
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve

# Symlink the CLI
mkdir -p ~/.local/bin
ln -sf ~/.agenticEvolve/ae ~/.local/bin/ae

# Make sure ~/.local/bin is in your PATH
# Add to ~/.zshrc or ~/.bashrc if needed:
# export PATH="$HOME/.local/bin:$PATH"

# Initialize (populates memory files, validates collectors)
ae init
```

### Configure (optional)

Edit `~/.agenticEvolve/config.sh`:

```bash
# Cost caps
DAILY_CAP=5        # USD per day
WEEKLY_CAP=25      # USD per week

# Telegram bot (create via @BotFather)
TELEGRAM_BOT_TOKEN="your-token"
TELEGRAM_CHAT_ID="your-chat-id"

# Brave Search API (for X/Twitter signal collection)
BRAVE_API_KEY="your-key"
```

## Usage

```bash
# Run one full cycle (collect → analyze → build → review)
ae cycle

# Collect signals only
ae collect              # all sources
ae collect github       # just GitHub
ae collect hackernews   # just HN

# Check system status
ae status

# Review queued skills interactively
ae review

# Approve or reject a specific skill
ae approve <skill-name>
ae reject <skill-name>

# View memory
ae state                # curated knowledge
ae log 20               # last 20 lines of raw log
ae watchlist            # monitored accounts/keywords

# Cost tracking
ae cost                 # breakdown (today / week / all time)
ae cost check           # exit 0 if under cap, exit 1 if over

# Manage watchlist
ae watchlist add github anthropics
ae watchlist rm github anthropics

# Cron management
ae start                # enable (cycle every 2h, GC weekly)
ae stop                 # disable
ae pause 4              # pause for 4 hours
```

## Signal collectors

| Source | Method | Auth required |
|--------|--------|---------------|
| GitHub | `gh` CLI (search API, starred repos, releases) | GitHub CLI auth |
| Hacker News | Algolia API | None |
| X/Twitter | Brave Search (`site:x.com`) | Brave API key |
| Discord | Planned (Phase 2) | — |
| WeCom/WeChat | Planned (Phase 2) | — |
| WhatsApp | Planned (Phase 2) | — |

## How skills get built

1. Collector finds a signal (e.g., a trending repo or HN post about a new dev tool)
2. Analyzer scores it on relevance, actionability, and novelty — picks the top one
3. Builder creates a Claude Code skill (`SKILL.md` with YAML frontmatter) in `skills-queue/`
4. Reviewer validates security (no hardcoded secrets), quality (clear instructions, <100 lines), and correctness
5. If approved by reviewer, skill goes to Telegram for human approval
6. Human approves → skill moves to `~/.claude/skills/` and is available in all future Claude Code sessions

## Inspiration

- [snarktank/ralph](https://github.com/snarktank/ralph) — primary inspiration (113-line bash orchestrator, two-tier learning, fresh context each cycle)
- [Anthropic's harness engineering research](https://www.anthropic.com/) — initializer agent pattern, inner/outer loop framing
- [OpenAI's multi-agent patterns](https://openai.com/) — deterministic linters, struggle-as-signal feedback loops

## License

Private. Not for redistribution.
