# Build Plan: Personal Closed-loop Agentic System

> Author: Vincent So (@outsmartchad)
> Date: 2026-03-11
> Philosophy: Keep the harness dumb. The intelligence belongs in the LLM, not the orchestration. (inspired by snarktank/ralph — 113 lines of bash)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        OUTER LOOP (cron)                        │
│  ~150 lines of bash. Runs on schedule. Fresh context each cycle.│
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Signal       │  │  Analyzer    │  │  Skill       │         │
│  │  Collectors   │→ │  Agent       │→ │  Builder     │         │
│  │  (bash/curl)  │  │  (claude -p) │  │  (claude -p) │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         ↑                                    ↓                  │
│         │            ┌──────────────┐        │                  │
│         └────────────│  Memory      │←───────┘                  │
│                      │  (files)     │                           │
│                      └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

Three stages per cycle:
1. **Collect** — bash scripts pull signals via APIs
2. **Analyze** — single `claude -p` call reads signals, writes action items
3. **Act** — single `claude -p` call builds one skill per cycle, reviewer validates

Each stage is a **fresh, stateless Claude invocation**. No session continuity. If one cycle goes off-rails, the next starts clean.

---

## Phase 0: Initializer Agent (First Run Only)

From Anthropic's harness engineering research: the very first run uses a specialized prompt that scaffolds the entire environment. This only runs once — every subsequent cycle uses the regular loop.

### What the initializer does

A single `claude -p` call with `prompts/initialize.md`:

1. Create `~/.agenticEvolve/` directory structure (collectors, prompts, signals, memory, skills-queue, archive, logs)
2. Write `config.sh` with sensible defaults (daily cap $5, poll interval 2hr)
3. Write initial `memory/watchlist.md` with starter accounts and keywords:
   - GitHub: `anthropics`, `openai`, `snarktank`, `openclaw`, top Claude Code contributors
   - X: `@AnthropicAI`, `@OpenAI`, `@alexalbert__`, `@aabordes`, key AI builders
   - Keywords: `claude code`, `mcp server`, `agent loop`, `agentic workflow`, `harness engineering`, `dev tool`
   - HN: `Show HN` + keyword matches
4. Write initial `memory/state.md` with bootstrap learnings (e.g., "Check Anthropic engineering blog weekly", "GitHub trending repos with >50 stars in 24h have highest signal")
5. Write empty `memory/log.md` with header
6. Write empty `memory/action-items.md`
7. Write empty `logs/cost.log`
8. Verify all collector scripts exist and are executable
9. Run one test collection cycle (GitHub + HN + X) to validate APIs
10. Output `<promise>INITIALIZED</promise>` on success

### Why a separate initializer?

Anthropic found this critical. Without it, the first coding agent wastes its entire context window figuring out the environment. With it, every subsequent cycle starts with a clean, well-documented workspace.

```bash
# First-time setup (run once, manually)
claude -p "$(cat ~/.agenticEvolve/prompts/initialize.md)" \
    --model sonnet \
    --dangerously-skip-permissions \
    --print
```

---

## Phase 1: Signal Collectors (Ingest Layer)

Each collector is a standalone bash script. No Node.js, no frameworks.

### Platforms & Methods

| Platform | Method | What to collect |
|----------|--------|-----------------|
| **GitHub** | `gh` CLI | Trending repos, starred repo activity, issues/PRs from followed people, release notes |
| **Hacker News** | HN Algolia API (`hn.algolia.com/api/v1`) | Top stories, Show HN, keyword searches |
| **X (Twitter)** | Brave Search `site:x.com` | Tweets from specific accounts (Anthropic employees, AI builders), keyword searches |
| **Discord** | Discord bot (phase 2) | Messages from specific channels (Claude Code, AI agents, dev tools communities) |
| **WeChat (WeCom)** | WeCom Bot API (phase 2). Pattern from `OpenClaw-Wechat`. | Group messages, article shares, personal WeChat interop |
| **WhatsApp** | Baileys (phase 3). Auth pattern from OpenClaw. | Group messages from builder communities |

### Common Signal Format

```json
{
  "id": "unique-id",
  "source": "github|hn|x|discord|wechat|whatsapp",
  "timestamp": "2026-03-11T15:30:00Z",
  "author": "username",
  "title": "optional title",
  "content": "the actual text/body",
  "url": "link to original",
  "metadata": {
    "stars": 100,
    "replies": 50,
    "relevance_tags": ["claude-code", "mcp", "agent-loop"]
  }
}
```

### Implementation

- Start with **GitHub + HN + Brave Search for X** (easiest, no auth complexity)
- Store raw signals as JSON files in `signals/YYYY-MM-DD/`
- Each collector is a bash script using `curl` + `jq`
- Dedup: hash-based, skip signals already in `signal-history.db`

### Directory structure

```
~/.agenticEvolve/
├── run-cycle.sh           # ~150 lines — the entire orchestrator
├── config.sh              # cost caps, poll interval, watchlist path
├── collectors/
│   ├── github.sh          # gh CLI based
│   ├── hackernews.sh      # curl + jq against Algolia API
│   └── x-search.sh        # Brave Search with site:x.com
├── prompts/
│   ├── initialize.md      # first-run initializer prompt (Phase 0)
│   ├── analyze.md         # analyzer prompt (the intelligence)
│   ├── build-skill.md     # skill builder prompt (the intelligence)
│   ├── review-skill.md    # reviewer prompt (Read-only validation)
│   └── gc.md              # weekly garbage collection prompt
├── run-gc.sh              # ~30 lines — weekly maintenance
├── notify.sh              # ~40 lines — Telegram notifications
├── telegram-listener.sh   # ~60 lines — approve/reject callbacks
├── ae                     # CLI entrypoint (see Commands section)
├── signals/               # raw collected signals (JSON per day)
├── memory/                # persistent state (see Phase 4)
├── skills-queue/          # skills pending human review
├── archive/               # auto-archived old cycles
└── logs/                  # cycle logs
```

---

## Commands (`ae` CLI)

Single entrypoint: `ae <command>`. Symlinked to `~/.local/bin/ae` so it works globally. Used by you manually AND by agents in prompts.

### For you (human)

| Command | What it does |
|---------|-------------|
| `ae init` | Run Phase 0 initializer (first time only) |
| `ae cycle` | Run one full cycle manually (collect → analyze → build → review) |
| `ae status` | Show system status: last cycle, pending items, cost today, queue |
| `ae review` | List skills in queue, approve/reject interactively |
| `ae approve <skill>` | Move skill from queue to `~/.claude/skills/` |
| `ae reject <skill>` | Delete skill from queue, log reason |
| `ae watchlist` | Show current watchlist |
| `ae watchlist add <type> <value>` | Add to watchlist (e.g., `ae watchlist add github anthropics`) |
| `ae watchlist rm <type> <value>` | Remove from watchlist |
| `ae collect` | Run collectors only (no analysis) |
| `ae collect github` | Run single collector |
| `ae cost` | Show cost today / this week / this month |
| `ae log` | Tail last 50 lines of `log.md` |
| `ae state` | Show `state.md` (curated learnings) |
| `ae gc` | Run garbage collection manually |
| `ae start` | Enable cron jobs (cycle + gc) |
| `ae stop` | Disable cron jobs |
| `ae pause` | Skip next N cycles (e.g., `ae pause 3`) |

### For agents (used in prompts)

Agents call the same `ae` commands. This keeps prompts clean — instead of writing raw file paths, the prompt says "run `ae collect` to gather signals."

| Command | Used by | Why |
|---------|---------|-----|
| `ae collect` | Analyzer prompt | Gather fresh signals before analysis |
| `ae state` | All agents | Read curated learnings first |
| `ae log --last 20` | Analyzer | Check recent failures before picking next action |
| `ae queue <skill>` | Skill builder | Place finished skill in review queue |
| `ae queue ls` | Reviewer | List skills pending review |
| `ae approve <skill>` | Telegram listener | Move approved skill to `~/.claude/skills/` |
| `ae reject <skill> --reason "..."` | Telegram listener / Reviewer | Delete + log reason |
| `ae notify <message>` | Any agent | Send a message to Telegram |
| `ae cost check` | Orchestrator | Check if daily cap reached (exit 0 = ok, exit 1 = exceeded) |

### Implementation

Single bash script `ae` (~200 lines) with a `case` statement:

```bash
#!/bin/bash
set -euo pipefail

EXODIR="$HOME/.agenticEvolve"
source "$EXODIR/config.sh"

case "${1:-help}" in
    init)
        claude -p "$(cat $EXODIR/prompts/initialize.md)" \
            --model sonnet --dangerously-skip-permissions --print
        ;;
    cycle)
        bash "$EXODIR/run-cycle.sh"
        ;;
    status)
        echo "=== agenticEvolve status ==="
        echo "Last cycle: $(ls -t $EXODIR/logs/2*.log 2>/dev/null | head -1)"
        echo "Action items: $(grep -c '^\- \[ \]' $EXODIR/memory/action-items.md 2>/dev/null || echo 0) pending"
        echo "Skills in queue: $(ls $EXODIR/skills-queue/ 2>/dev/null | wc -l | tr -d ' ')"
        echo "Cost today: $(tail -1 $EXODIR/logs/cost.log 2>/dev/null | awk '{print "$"$4}' || echo '$0')"
        ;;
    review)
        for skill in "$EXODIR/skills-queue"/*/; do
            [ -d "$skill" ] || continue
            name=$(basename "$skill")
            echo "--- $name ---"
            cat "$skill/SKILL.md"
            echo ""
            read -p "Approve (a), Reject (r), Skip (s)? " choice
            case "$choice" in
                a) mv "$skill" "$HOME/.claude/skills/$name" && echo "Approved: $name" ;;
                r) rm -rf "$skill" && echo "Rejected: $name" ;;
                *) echo "Skipped" ;;
            esac
        done
        ;;
    approve)
        mv "$EXODIR/skills-queue/$2" "$HOME/.claude/skills/$2"
        echo "Approved: $2"
        ;;
    reject)
        reason="${4:-no reason given}"
        echo "## $(date -Iseconds) — Rejected: $2 — $reason" >> "$EXODIR/memory/log.md"
        rm -rf "$EXODIR/skills-queue/$2"
        echo "Rejected: $2"
        ;;
    watchlist)
        case "${2:-show}" in
            show) cat "$EXODIR/memory/watchlist.md" ;;
            add)  echo "- $3: $4" >> "$EXODIR/memory/watchlist.md" && echo "Added: $3 $4" ;;
            rm)   sed -i '' "/$4/d" "$EXODIR/memory/watchlist.md" && echo "Removed: $4" ;;
        esac
        ;;
    collect)
        if [ -n "${2:-}" ]; then
            bash "$EXODIR/collectors/$2.sh"
        else
            bash "$EXODIR/collectors/github.sh" || true
            bash "$EXODIR/collectors/hackernews.sh" || true
            bash "$EXODIR/collectors/x-search.sh" || true
        fi
        ;;
    cost)
        echo "=== Cost ==="
        echo "Today: $(grep "$(date +%Y-%m-%d)" $EXODIR/logs/cost.log 2>/dev/null | awk '{sum+=$3} END{printf "$%.2f", sum}')"
        echo "Cumulative: $(tail -1 $EXODIR/logs/cost.log 2>/dev/null | awk '{printf "$%.2f", $4}')"
        ;;
    cost\ check)
        CUMULATIVE=$(tail -1 "$EXODIR/logs/cost.log" 2>/dev/null | awk '{print $4}' || echo "0")
        awk "BEGIN{exit ($CUMULATIVE >= $DAILY_CAP)}"
        ;;
    state)   cat "$EXODIR/memory/state.md" ;;
    log)     tail -${2:-50} "$EXODIR/memory/log.md" ;;
    queue)
        case "${2:-ls}" in
            ls) ls "$EXODIR/skills-queue/" 2>/dev/null || echo "Queue empty" ;;
            *)  mkdir -p "$EXODIR/skills-queue/$2" && echo "Queued: $2" ;;
        esac
        ;;
    gc)      bash "$EXODIR/run-gc.sh" ;;
    start)
        (crontab -l 2>/dev/null; echo "0 */2 * * * $EXODIR/run-cycle.sh") | sort -u | crontab -
        (crontab -l 2>/dev/null; echo "0 3 * * 0 $EXODIR/run-gc.sh") | sort -u | crontab -
        echo "Cron jobs enabled."
        ;;
    stop)
        crontab -l 2>/dev/null | grep -v agenticEvolve | crontab -
        echo "Cron jobs disabled."
        ;;
    notify)  bash "$EXODIR/notify.sh" "$2" ;;
    help|*)
        echo "ae — agenticEvolve CLI"
        echo ""
        echo "  ae init              First-time setup"
        echo "  ae cycle             Run one full cycle"
        echo "  ae status            System status"
        echo "  ae review            Interactive skill review"
        echo "  ae approve <skill>   Approve a queued skill"
        echo "  ae reject <skill>    Reject a queued skill"
        echo "  ae watchlist         Show/add/rm watchlist entries"
        echo "  ae collect [source]  Run collectors"
        echo "  ae cost              Show cost breakdown"
        echo "  ae state             Show curated learnings"
        echo "  ae log [N]           Tail last N lines of log"
        echo "  ae queue [ls|name]   List or add to skill queue"
        echo "  ae gc                Run garbage collection"
        echo "  ae start             Enable cron jobs"
        echo "  ae stop              Disable cron jobs"
        echo "  ae notify <msg>      Send Telegram notification"
        ;;
esac
```

### Installation

```bash
chmod +x ~/.agenticEvolve/ae
ln -sf ~/.agenticEvolve/ae ~/.local/bin/ae
```

---

## Phase 2: Analyzer Agent (Filter & Rank)

A single `claude -p` call. Fresh context. Reads signals + memory, outputs action items.

### What the analyzer does

1. Read `memory/state.md` FIRST (curated patterns section — from Ralph's two-tier learning)
2. Read new signals since last run
3. Read `memory/watchlist.md` for what to look for
4. Score each signal on: **relevance**, **actionability**, **novelty**
5. Pick the **single most actionable item** (one task per cycle — from Ralph)
6. Write action item to `memory/action-items.md`
7. Append raw findings to `memory/log.md` (append-only, never replace)
8. Update `memory/state.md` with curated learnings (deduplicated, general)
9. If nothing actionable: output `<promise>NOTHING_ACTIONABLE</promise>`

### Completion signal (from Ralph)

```bash
if echo "$OUTPUT" | grep -q "<promise>NOTHING_ACTIONABLE</promise>"; then
    # reduce poll frequency on next cron run
fi
```

Simple grep. No structured status blocks. No JSON parsing of agent output.

### Filtering heuristics

- Keywords: `claude code`, `mcp server`, `agent loop`, `skill`, `agentic workflow`, `cursor`, `codex`, `dev tool`, `productivity`, `automation`
- Authors: maintain a list of high-signal accounts in `watchlist.md`
- Engagement: HN > 50 points, GitHub > 20 stars in 24h, X > 100 likes
- Dedup: skip signals already processed (hash in `signal-history.db`)

---

## Phase 3: Skill Builder (Output Layer)

When the analyzer identifies something worth building, the skill builder creates it. One skill per cycle.

### What it produces

| Input signal | Output |
|-------------|--------|
| New tool/library discovered | Claude Code skill wrapping it |
| Useful workflow pattern | Skill with step-by-step instructions |
| New MCP server available | `claude mcp add` command + docs |
| Useful prompt pattern | Skill or CLAUDE.md update |
| New API/service | Skill with API integration (like we did with Brave Search) |

### Auto-build flow

1. Analyzer writes action item to `memory/action-items.md`
2. Skill builder reads the top action item, runs as fresh `claude -p`:
   a. Research the tool/pattern (read docs, fetch URLs)
   b. Write SKILL.md with proper frontmatter
   c. Place in `skills-queue/<skill-name>/SKILL.md`
3. **Reviewer agent** — a separate, tool-restricted `claude -p` (Read-only) validates:
   - Security (no leaked keys, no unsafe bash)
   - Redundancy with existing skills
   - SKILL.md frontmatter syntax
   - If rejected: discard with reason logged to `memory/log.md`
4. **Human review gate** — skills in queue are NOT auto-installed
5. You review with `/agenticEvolve-review` → approve → moves to `~/.claude/skills/`

### Why three gates?

1. Reviewer agent catches obvious issues automatically
2. Human review catches subtle issues and makes the final call
3. Skills modify Claude's behavior — bad skills compound over time

---

## Phase 4: Memory & State (Persistence Layer)

Two-tier learning system (from Ralph). All files. No databases for the core loop.

### State files

```
~/.agenticEvolve/memory/
├── state.md            # CURATED: what the system knows — learnings, failure lessons, reusable insights (read FIRST)
├── log.md              # RAW: what happened — append-only, includes skill builds, failures, everything (never edit)
├── action-items.md     # what to do next — grep for "- [ ]", pick the top one
└── watchlist.md        # what to look for — accounts, repos, keywords
```

Operational files live outside memory:
- `logs/cost.log` — spend tracking (one line per cycle)
- `signal-history.db` (SQLite) — dedup only, not in critical path

### Two-tier learning (from Ralph)

- **`state.md`** (top tier): Curated, deduplicated. What the system knows right now. Includes both positive learnings ("Anthropic ships MCP updates on Tuesdays") and failure lessons ("Notion API requires auth — skip unless key configured"). Read first every cycle. The analyzer updates it; the GC agent deduplicates it.
- **`log.md`** (bottom tier): Raw append-only. Everything that happened — signal analysis results, skills built, failures, GC summaries. Never edited, never truncated (GC archives old entries).

### CLAUDE.md as persistent memory (from Ralph)

Learnings that apply broadly get written to `~/.claude/CLAUDE.md` or `~/.claude/rules/*.md`. This outlives the agenticEvolve loop — future Claude Code sessions benefit even when the loop isn't running.

### Archive-on-context-change (from Ralph)

When `watchlist.md` changes focus significantly (e.g., new project), auto-archive:
```
~/.agenticEvolve/archive/YYYY-MM-DD-<context>/
├── state.md
├── log.md
├── action-items.md
└── skill-changelog.md
```

### Cost tracking

Simple — one line per cycle appended to `logs/cost.log` (operational, not memory):
```
2026-03-11T15:30:00Z  cycle-42  0.12  3.45
```
Before each cycle, check cumulative cost against daily cap ($5 default). If exceeded, skip until tomorrow.

---

## Phase 5: Orchestration (The Loop)

### The entire orchestrator (`run-cycle.sh`)

Target: **~150 lines of bash**. Not 2000.

```bash
#!/bin/bash
set -euo pipefail

EXODIR="$HOME/.agenticEvolve"
source "$EXODIR/config.sh"
LOG="$EXODIR/logs/$(date +%Y-%m-%d_%H%M).log"

# --- Cost check ---
CUMULATIVE=$(tail -1 "$EXODIR/logs/cost.log" 2>/dev/null | awk '{print $4}' || echo "0")
if awk "BEGIN{exit !($CUMULATIVE >= $DAILY_CAP)}"; then
    echo "Daily cost cap reached (\$$CUMULATIVE). Skipping." >> "$LOG"
    exit 0
fi

# --- 1. Collect signals ---
echo "=== Collecting signals ===" >> "$LOG"
bash "$EXODIR/collectors/github.sh" >> "$LOG" 2>&1 || true
bash "$EXODIR/collectors/hackernews.sh" >> "$LOG" 2>&1 || true
bash "$EXODIR/collectors/x-search.sh" >> "$LOG" 2>&1 || true

# --- 2. Analyze (fresh Claude instance) ---
echo "=== Analyzing ===" >> "$LOG"
OUTPUT=$(claude -p "$(cat $EXODIR/prompts/analyze.md)" \
    --model sonnet \
    --output-format json \
    --dangerously-skip-permissions \
    --print 2>&1 | tee /dev/stderr) || true

# Log cost
COST=$(echo "$OUTPUT" | jq -r '.total_cost_usd // "0"' 2>/dev/null || echo "0")
CUMULATIVE=$(awk "BEGIN{print $CUMULATIVE + $COST}")
echo "$(date -Iseconds) analyze $COST $CUMULATIVE" >> "$EXODIR/logs/cost.log"

# Check for nothing actionable
if echo "$OUTPUT" | grep -q "<promise>NOTHING_ACTIONABLE</promise>"; then
    echo "Nothing actionable this cycle." >> "$LOG"
    exit 0
fi

# --- 3. Build one skill (fresh Claude instance) ---
echo "=== Building skill ===" >> "$LOG"
OUTPUT=$(claude -p "$(cat $EXODIR/prompts/build-skill.md)" \
    --model sonnet \
    --output-format json \
    --dangerously-skip-permissions \
    --print 2>&1 | tee /dev/stderr) || true

COST=$(echo "$OUTPUT" | jq -r '.total_cost_usd // "0"' 2>/dev/null || echo "0")
CUMULATIVE=$(awk "BEGIN{print $CUMULATIVE + $COST}")
echo "$(date -Iseconds) build $COST $CUMULATIVE" >> "$EXODIR/logs/cost.log"

# --- 4. Review skill (fresh Claude instance, Read-only) ---
if ls "$EXODIR/skills-queue/"*/SKILL.md 1>/dev/null 2>&1; then
    echo "=== Reviewing skill ===" >> "$LOG"
    claude -p "$(cat $EXODIR/prompts/review-skill.md)" \
        --model sonnet \
        --output-format json \
        --dangerously-skip-permissions \
        --allowedTools "Read" \
        --print >> "$LOG" 2>&1 || true
fi

# --- 5. Notify via Telegram ---
bash "$EXODIR/notify.sh" "$LOG"

echo "=== Cycle complete ===" >> "$LOG"
```

### Scheduling

Start with cron:
```bash
0 */2 * * * ~/.agenticEvolve/run-cycle.sh
```

That's it. No launchd daemon. No sentinel files. No state machines.

---

## Phase 6: Garbage Collection Agent (Periodic Maintenance)

From OpenAI's harness engineering: periodic agents that fight entropy and decay. Runs weekly (not every cycle).

### What the GC agent does

A single `claude -p` call with `prompts/gc.md`, scheduled weekly via cron:

1. **Prune stale action items** — remove items in `action-items.md` older than 14 days that were never acted on
2. **Detect unused skills** — scan `~/.claude/skills/` for skills not invoked in 30+ days (check shell history, logs)
3. **Deduplicate patterns** — read `memory/state.md`, merge redundant entries, remove outdated ones
4. **Trim log** — if `memory/log.md` exceeds 500 lines, archive old entries to `archive/log-YYYY-MM-DD.md`
5. **Validate collectors** — run each collector with a dry-run flag, report any that are broken (expired API keys, changed endpoints)
6. **Signal quality report** — analyze last 7 days of signals: which sources produced actionable items? Which produced only noise? Suggest watchlist updates.
7. Append GC summary to `memory/log.md`

### Scheduling

```bash
# Weekly on Sunday at 3am
0 3 * * 0 ~/.agenticEvolve/run-gc.sh
```

### `run-gc.sh` (~30 lines)

```bash
#!/bin/bash
set -euo pipefail

EXODIR="$HOME/.agenticEvolve"
LOG="$EXODIR/logs/gc-$(date +%Y-%m-%d).log"

echo "=== Garbage Collection ===" >> "$LOG"
claude -p "$(cat $EXODIR/prompts/gc.md)" \
    --model sonnet \
    --output-format json \
    --dangerously-skip-permissions \
    --print >> "$LOG" 2>&1 || true

echo "=== GC complete ===" >> "$LOG"
```

---

## Phase 7: Struggle-as-Signal Feedback Loop

From OpenAI's harness engineering: "When the agent struggles, treat it as a signal — identify what is missing and feed it back."

### How it works

When the analyzer or skill builder **fails** (non-zero exit, error in output, skill rejected by reviewer), the orchestrator:

1. Appends the failure to `memory/log.md` (raw record)
2. The **next cycle's analyzer** reads `log.md`, sees the failure, and:
   - Avoids repeating the same failed action
   - Updates `state.md` with the lesson (e.g., "Notion API requires auth — skip unless key configured")
   - Suggests environment fixes in `action-items.md` if needed (e.g., "configure missing API key")

### In the orchestrator

Add to `run-cycle.sh` after each Claude call:

```bash
# After skill builder
if echo "$OUTPUT" | grep -q "<promise>BUILD_FAILED</promise>"; then
    echo "## $(date -Iseconds) — BUILD_FAILED" >> "$EXODIR/memory/log.md"
    echo "$OUTPUT" | tail -5 >> "$EXODIR/memory/log.md"
fi
```

### Why this matters

This is the **self-evolution mechanism**. Without it, the system repeats the same mistakes every cycle. With it, failures become learnings — the system gets smarter about what it can and can't do.

---

## Phase 8: Telegram Bot (Notification + Mobile Review)

One bot. Not three. The coordination happens through files — the bot is just the notification and approval layer.

### What the bot does

1. **Post-cycle summary** — after each cycle, sends:
   ```
   🔄 Cycle #42 complete
   📡 Signals: 8 github, 3 hn, 1 x
   ✅ Built skill: mcp-notion (waiting in review queue)
   💰 Cost: $0.14 (daily: $2.30 / $5.00)
   ```

2. **Skill approval inline** — when a skill is queued, sends the SKILL.md content with two buttons: `Approve` / `Reject`. You tap from your phone → skill moves to `~/.claude/skills/` or gets deleted.

3. **Failure alerts** — when analyzer or skill builder fails:
   ```
   ⚠️ Skill builder failed
   Action: Build MCP server for Notion API
   Reason: Could not fetch docs (403)
   Logged to state.md
   ```

4. **Weekly GC report** — after `run-gc.sh`:
   ```
   🧹 Weekly cleanup
   Pruned: 3 stale action items
   Unused skills: brave-search (30+ days)
   Signal quality: GitHub 80% actionable, HN 20%, X 40%
   ```

5. **Nothing actionable** — suppressed by default. Optional: send a quiet "😴 Nothing actionable" so you know it's alive.

### Implementation

Single bash script `notify.sh` (~40 lines) using Telegram Bot API:

```bash
#!/bin/bash
# notify.sh — send cycle summary to Telegram
set -euo pipefail

source "$HOME/.agenticEvolve/config.sh"
# config.sh has: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

send() {
    curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$1" \
        -d parse_mode="Markdown" > /dev/null
}

# Parse the log for summary
LOG="$1"
SIGNALS=$(grep -c "signal collected" "$LOG" 2>/dev/null || echo "0")
SKILL=$(grep -o "skills-queue/[^/]*" "$LOG" 2>/dev/null | head -1 || echo "none")
COST=$(tail -1 "$HOME/.agenticEvolve/logs/cost.log" 2>/dev/null | awk '{print $3, $4}' || echo "0 0")

send "🔄 *Cycle complete*
📡 Signals processed: $SIGNALS
🛠 Skill built: \`$SKILL\`
💰 Cost: \$$COST"
```

### Skill approval via Telegram

For inline approve/reject, use Telegram's inline keyboard:

```bash
send_skill_for_review() {
    SKILL_NAME="$1"
    SKILL_CONTENT=$(cat "$HOME/.agenticEvolve/skills-queue/$SKILL_NAME/SKILL.md" | head -30)
    
    curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="📋 *New skill for review:* \`$SKILL_NAME\`

\`\`\`
$SKILL_CONTENT
\`\`\`" \
        -d parse_mode="Markdown" \
        -d reply_markup='{"inline_keyboard":[[{"text":"✅ Approve","callback_data":"approve:'$SKILL_NAME'"},{"text":"❌ Reject","callback_data":"reject:'$SKILL_NAME'"}]]}' \
        > /dev/null
}
```

To handle button callbacks, run a lightweight polling loop (or webhook) that:
- On `approve:<skill>`: moves `skills-queue/<skill>/` → `~/.claude/skills/<skill>/`
- On `reject:<skill>`: deletes `skills-queue/<skill>/`, logs reason to `log.md`

This can be a simple `telegram-listener.sh` running as a background process or launchd job.

### Setup

1. Create bot via @BotFather on Telegram → get `TELEGRAM_BOT_TOKEN`
2. Send a message to the bot → get `TELEGRAM_CHAT_ID` via `getUpdates` API
3. Add both to `config.sh`:
   ```bash
   TELEGRAM_BOT_TOKEN="your-token"
   TELEGRAM_CHAT_ID="your-chat-id"
   ```

### Files to create

```
~/.agenticEvolve/
├── notify.sh              # ~40 lines — sends cycle summary to Telegram
└── telegram-listener.sh   # ~60 lines — polls for approve/reject button callbacks
```

---

## Phase 9: Review & Evolution Skills

### `/agenticEvolve-review` — review pending skills

```yaml
---
name: agenticEvolve-review
description: Review and approve/reject skills built by agenticEvolve
disable-model-invocation: true
---

Review all pending skills in ~/.agenticEvolve/skills-queue/:
1. List each skill with its SKILL.md content
2. Show the source signal that triggered it
3. For each, ask: approve (move to ~/.claude/skills/), reject (delete), or edit
```

### `/agenticEvolve-status` — check system status

```yaml
---
name: agenticEvolve-status
description: Show agenticEvolve system status
disable-model-invocation: true
---

Show current agenticEvolve status:
1. Last cycle time and result (tail logs)
2. Signals collected today (count files in signals/today)
3. Action items pending (read memory/action-items.md)
4. Skills in queue (ls skills-queue/)
5. Cost today (tail logs/cost.log)
6. Read memory/state.md (curated insights)
```

### `/agenticEvolve-watchlist` — manage what to track

```yaml
---
name: agenticEvolve-watchlist
description: Manage agenticEvolve watchlist - accounts, repos, keywords to track
disable-model-invocation: true
---

Manage ~/.agenticEvolve/memory/watchlist.md:
- Add/remove GitHub accounts to follow
- Add/remove X accounts to monitor
- Add/remove keywords to search
- Add/remove Discord channels to watch
```

---

## Build Order (Priority)

### Week 1: Foundation
- [ ] Write `ae` CLI entrypoint (~200 lines) + symlink to `~/.local/bin/ae`
- [ ] Write initializer prompt (`prompts/initialize.md`) — Phase 0
- [ ] Run `ae init` to scaffold `~/.agenticEvolve/` (config, watchlist, memory)
- [ ] Build GitHub signal collector (`ae collect github`)
- [ ] Build HN signal collector (`ae collect hackernews`)
- [ ] Build X signal collector (`ae collect x`)
- [ ] Create common signal format + storage
- [ ] Write analyzer prompt (`prompts/analyze.md`)

### Week 2: Loop & Memory
- [ ] Write `run-cycle.sh` orchestrator (~150 lines)
- [ ] Write skill builder prompt (`prompts/build-skill.md`)
- [ ] Write reviewer prompt (`prompts/review-skill.md`)
- [ ] Create two-tier memory (state.md + log.md)
- [ ] Add cost tracking (logs/cost.log + daily cap check)
- [ ] Set up cron job
- [ ] Test full cycle end-to-end

### Week 3: Skills & Telegram
- [ ] Build `/agenticEvolve-review` skill
- [ ] Build `/agenticEvolve-status` skill
- [ ] Build `/agenticEvolve-watchlist` skill
- [ ] Add struggle-as-signal feedback loop to `run-cycle.sh`
- [ ] Set up Telegram bot (@BotFather)
- [ ] Write `notify.sh` (~40 lines — cycle summaries)
- [ ] Write `telegram-listener.sh` (~60 lines — approve/reject callbacks)
- [ ] Add archive-on-context-change
- [ ] Add dedup (signal-history.db)
- [ ] Write GC prompt (`prompts/gc.md`) + `run-gc.sh`
- [ ] Set up weekly GC cron job
- [ ] Log rotation

### Future: Phase 2 Platforms
- [ ] Discord bot collector
- [ ] WeCom collector (pattern from OpenClaw-Wechat)
- [ ] WhatsApp collector (Baileys, auth from OpenClaw)
- [ ] RSS feed collector (blogs, substacks)

### Future: Advanced (only if needed)
- [ ] Discord webhook notifications (in addition to Telegram)
- [ ] Self-assessment: track which skills actually get used
- [ ] Prune unused skills automatically
- [ ] Agent Teams for parallel analysis

---

## Connector Reference (for Phase 2 platforms)

We build lightweight collectors but borrow patterns from OpenClaw extensions.

| Connector | Source to copy from | What to take | npm deps |
|-----------|-------------------|--------------|----------|
| **Discord** | `openclaw/extensions/discord/` | Config schema, bot token pattern | `discord.js` |
| **WeCom** | `dingxiang-me/OpenClaw-Wechat` | XML/JSON callback parsing, verification, webhook outbound | none (`http`/`crypto`) |
| **WhatsApp** | `openclaw/extensions/whatsapp/` | QR/linked-device auth flow, Baileys session persistence | `@whiskeysockets/baileys` |

### WeCom connector details

WeCom (Enterprise WeChat) is the recommended WeChat integration:
- **Official API** — no ban risk
- **Two modes**: Agent mode (custom app) or Bot mode (intelligent bot, streaming)
- **Personal WeChat interop** — WeCom <-> personal WeChat messaging works
- **Webhook outbound** — push digests to group chats
- **Reference**: [`dingxiang-me/OpenClaw-Wechat`](https://github.com/dingxiang-me/OpenClaw-Wechat)
- **Needs**: WeCom admin account (free), create app/bot, public callback URL

---

## Patterns Borrowed

| Pattern | From | How we use it |
|---------|------|--------------|
| Two-tier learning | Ralph (snarktank) | `state.md` (curated) + `log.md` (raw append-only) |
| Fresh context each iteration | Ralph (snarktank) | No session continuity. Each `claude -p` starts clean. |
| One task per cycle | Ralph (snarktank) | Analyzer picks one action item. Skill builder builds one skill. |
| `<promise>` completion signal | Ralph (snarktank) | Simple grep for `<promise>NOTHING_ACTIONABLE</promise>` |
| CLAUDE.md as persistent memory | Ralph (snarktank) | Broad learnings written to `~/.claude/rules/*.md`, outlives the loop |
| Archive-on-context-change | Ralph (snarktank) | Auto-archive old memory when focus shifts |
| Dual-agent review pass | continuous-claude | Separate reviewer validates skills before queuing |
| Cost tracking | continuous-claude | `cost.log` + daily cap check before each cycle |
| Heartbeat pattern | OpenClaw | Periodic wake-up on cron schedule |
| Channel connectors | OpenClaw + OpenClaw-Wechat | Config schemas, auth flows for Phase 2 platforms |
| Initializer agent | Anthropic harness eng. | First-run agent scaffolds environment with sensible defaults |
| Garbage collection agent | OpenAI harness eng. | Weekly agent prunes stale items, detects unused skills, fights entropy |
| Struggle-as-signal | OpenAI harness eng. | Failures logged to `log.md`, lessons curated into `state.md` by next analyzer |
| Review gate | Original | Human approves skills before installation |

### What we deliberately cut

| Cut | Was from | Why |
|-----|----------|-----|
| Circuit breaker | Ralph fork (frankbria) | Fresh context each cycle handles this. Bad cycle? Next one starts clean. |
| Structured status blocks | Ralph fork | `<promise>` tag + grep is simpler. Let the LLM write freeform. |
| Consensus relay baton | auto-company | Replaced by two-tier learning (state.md + log.md). One file pattern, not three. |
| Session continuity (`--resume`) | Ralph fork | Fresh context is a feature. Prevents accumulated confusion. |
| Completion signal quorum (3x) | continuous-claude | Single `<promise>` signal is enough. Simpler. |
| Git worktree parallelism | continuous-claude | Premature optimization. Serial is fine. |
| PR-as-validation-gate | continuous-claude | Overkill for personal skills. Reviewer agent + human review is enough. |
| Claude-as-committer | continuous-claude | We're not making code PRs. No git commits in the loop. |
| Expert personas | auto-company | One analyzer agent is enough. No need for 14 personas. |
| Convergence rules | auto-company | One task per cycle already forces convergence. |

---

## Key Design Decisions

1. **~150 lines of bash** — the intelligence is in the prompts, not the orchestrator.
2. **Fresh context each cycle** — no session state, no accumulated confusion.
3. **One task per cycle** — prevents scope creep, keeps context clean.
4. **Two-tier learning** — curated patterns (read first) + raw logs (append-only).
5. **Three gates for skills** — auto-reviewer → queue → human review.
6. **Sonnet for everything** — cost efficiency for high-frequency autonomous cycles.
7. **Brave Search for X** — no API auth complexity.
8. **Daily cost cap** — prevents runaway spend on autonomous system.
9. **No frameworks, no Node.js in the core loop** — bash + curl + jq + claude CLI.
10. **CLAUDE.md as escape hatch** — learnings that transcend the loop get persisted globally.

---

## Success Metrics

After 30 days:
- [ ] System has run 300+ cycles without manual intervention
- [ ] 10+ skills auto-generated and approved
- [ ] At least 3 skills actively used in daily work
- [ ] Signal-to-noise ratio improving (fewer irrelevant action items over time)
- [ ] Watchlist refined based on what actually produces useful signals
- [ ] Total cost < $150 for the month
