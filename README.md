# agenticEvolve

**A self-evolving AI agent — grows itself daily.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-33-orange?style=for-the-badge" alt="33 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-44-blue?style=for-the-badge" alt="44 Commands"></a>
</p>

**[简体中文](README.zh.md)** | **[繁體中文](README.zh-TW.md)** | **[日本語](README.ja.md)**

---

Persistent agent runtime built on `claude -p` with a Python asyncio gateway. 6-layer memory + cross-layer auto-recall. Closed-loop skill synthesis. Voice I/O. Browser automation. Built-in cron. 2-layer security. Multi-platform (Telegram + Discord + WhatsApp). Interactive CLI REPL with Rich TUI. 39 Telegram commands + 32 CLI commands — your entire dev machine in your pocket.

---

## What can you do with it?

**Browse the web for you**
> "Go to the Anthropic docs and find the latest Claude model pricing." The agent opens ABP browser, navigates, extracts the data, and sends you a clean summary. If Cloudflare blocks it, it auto-switches to Brave.

**Serve your WhatsApp and Discord groups**
> `/serve` → WhatsApp → Groups → toggle your dev group on. Now anyone in that group can talk to your AI agent. It responds to every message, maintains per-group conversation memory, and you control it all from Telegram inline keyboards. Works with Discord channels too — the agent hooks into your desktop app via Chrome DevTools Protocol.

**Subscribe to channels and get digests**
> `/subscribe` → Discord → pick your favorite channels. Next morning, run `/discord` and get a clean summary of everything you missed — key discussions, links shared, tools mentioned, action items. Works across Discord channels, WhatsApp groups, and WeChat groups. Never scroll through 500 unread messages again.

**Search your own WeChat history**
> WeChat's built-in search is terrible. The agent reads your local WeChat databases and gives you a searchable export — contacts, messages, groups, favorites. All offline, all on your machine.

**Absorb ideas from your group chats overnight**
> Your `/evolve` cron at 6 AM doesn't just scan GitHub. It also reads your WeChat tech group chats, summarizes the last 24 hours of discussions — new tools people mentioned, repos shared, techniques debated — and absorbs the best ideas into skills. You wake up with your group's collective intelligence baked in.

**Brainstorm business ideas from trending signals**
> `/produce` — the agent aggregates today's signals from 11 sources (GitHub Trending, Hacker News, X/Twitter, Reddit, Product Hunt, Lobste.rs, ArXiv, HuggingFace, BestOfJS, WeChat groups, and your starred repos), identifies emerging trends, and brainstorms 5 concrete app/business ideas with revenue models, tech stacks, and MVP scopes. Signal-driven ideation on demand.

**Self-improving UX**
> Every night at 1 AM, the agent reads the day's conversations, finds friction points where you waited too long or got confusing responses, and patches its own code to fix them. You wake up to a better agent.

**Ship code from your phone**
> You're on the subway. You text `/do add rate limiting to the API`. The agent reads your codebase, writes the middleware, runs the tests, and pushes to git. You get a summary back before your stop.

**Absorb any repo in one message**
> You see a cool repo on Twitter. Screenshot it to the bot. The agent OCRs the image, finds the GitHub URL, clones the repo, maps its architecture, extracts the patterns that matter to your stack, and installs them as skills — all from one photo.

**Wake up to new skills you didn't write**
> The daily `/evolve` cron fires at 6 AM. By the time you check Telegram, the agent has scanned GitHub trending, found a new testing framework, built a skill for it, passed it through 2-layer security, auto-installed it, and pushed to your repo. You just got smarter overnight.

**Talk to your codebase in any language**
> Send a voice message in English, Cantonese, Mandarin, Japanese, Korean, or any of 40+ supported languages. The agent transcribes locally via whisper.cpp (~500ms), auto-detects the language, responds in text, and reads the answer back to you in the same language via edge-tts.

**Deep-dive anything with `/learn`**
> `/learn https://github.com/some/repo` — the agent clones it, reads every file, maps the architecture, evaluates how it could benefit your workflow, gives an ADOPT / ADAPT / SKIP verdict, and optionally builds a skill from it.

---

## Capabilities

| Capability | Description |
|------------|-------------|
| **CLI REPL** | `ae` — Interactive Rich TUI with streaming output, markdown rendering, tool use spinners, 32 commands with Tab autocomplete, session persistence, auto-recall. No gateway required |
| **Multi-Platform** | Telegram (bot API) + Discord (local cache only) + WhatsApp (Baileys v7 bridge). `/subscribe` to monitor channels for digests, `/serve` to make the agent respond in any group or DM. WhatsApp supports images, PDFs, text files, and voice messages |
| **Build** | Full Claude Code over Telegram or CLI — terminal, file I/O, web search, MCP, 26 skills |
| **Evolve** | 5-stage pipeline: COLLECT → ANALYZE → BUILD → REVIEW → AUTO-INSTALL. Scans 12 sources: GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChat groups + Discord cache, synthesizes skills |
| **Absorb** | `/absorb <url>` — clones repo, maps architecture, diffs patterns, implements improvements into your system |
| **Learn** | `/learn <target>` — deep-dive extraction with ADOPT / ADAPT / SKIP verdicts |
| **Voice** | Send voice messages → local whisper.cpp transcription (~500ms). `/speak` → edge-tts with 300+ voices. Auto-detects Cantonese/Mandarin/Japanese/Korean |
| **Browser** | ABP (Agent Browser Protocol) for default browsing. Auto-switches to Brave/Chrome via CDP when Cloudflare blocks. Isolated agent profiles |
| **Auto-Recall** | `unified_search()` across 6 memory layers before every response (~400 tokens/msg) |
| **Cron** | `/loop every 6h /evolve` — autonomous growth on a schedule |
| **Security** | L1: regex scanner pre-install (reverse shells, credential theft, crypto miners). L2: AgentShield post-install (1282 tests, 102 rules). Auto-rollback on critical findings |
| **Hooks** | Typed async event system — `message_received`, `before_invoke`, `llm_output`, `tool_call`, `session_start`, `session_end` |
| **Semantic Recall** | TF-IDF cosine similarity search layer augments FTS5 keyword search. 5000-feature vectorizer with bigrams. Corpus rebuilt from sessions, learnings, instincts, memory files. Cached at `~/.agenticEvolve/cache/` |
| **Instinct Engine** | Behavioural pattern observations scored and routed to instincts table. High-confidence instincts (0.8+ across 2+ projects or 5+ sightings) auto-promote to MEMORY.md |
| **Resilience** | Drain-on-shutdown (30s wait for in-flight requests). Typed failure classification (auth/billing/rate-limit). 3-pass context compaction. Hot config reload. Loop detection (warn@3 identical turns, terminate@5). Memory queue read-through (debounced atomic writes, no stale reads). Parallel BUILD stage (ThreadPoolExecutor, 3 isolated workspaces) |
| **Testing** | 423 automated tests (423 pass, 1 xfail). Covers: 81 command handler integration tests (all 35+ handlers), session DB, FTS5 search, security scanner, signal dedup, semantic search, instinct promotion, cron parser, cost cap, loop detector, context compaction, flag parsing |

---

## Setup

### 1. Install

```bash
curl -fsSL https://raw.githubusercontent.com/outsmartchad/agenticEvolve/main/scripts/install.sh | bash
```

The installer handles everything — cloning, dependencies, PATH, and runs the interactive setup wizard. No prerequisites except Python 3 and git.

After installation:

```bash
source ~/.zshrc    # reload shell (or: source ~/.bashrc)
```

> **Requires:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`npm install -g @anthropic-ai/claude-code`) — the installer checks for it and shows the install command if missing.

### 2. Interactive Chat (CLI REPL)

```bash
ae
```

That's it. You get a Rich TUI with streaming output, markdown rendering, tool use spinners, and all 32 commands with Tab autocomplete. Resume a previous session with `ae --resume <session_id>`.

### 3. Start the Gateway (for Telegram/Discord/WhatsApp)

```bash
ae gateway start
```

Message your bot on Telegram, or let the agent serve your WhatsApp groups and Discord channels.

### Useful Commands

| Command | What it does |
|---------|-------------|
| `ae` | Interactive chat REPL (default) |
| `ae --resume ID` | Resume a previous session |
| `ae setup` | Re-run the setup wizard |
| `ae doctor` | Diagnose issues |
| `ae gateway start` | Start the messaging gateway |
| `ae gateway stop` | Stop the gateway |
| `ae gateway install` | Install as launchd service (auto-start on login) |
| `ae status` | System overview |
| `ae cost` | Usage and spend |

### Voice Support (optional)

```bash
brew install whisper-cpp ffmpeg
curl -L -o ~/.agenticEvolve/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

---

## Commands

All commands work in both the CLI REPL (`ae`) and Telegram. The CLI REPL supports Tab autocomplete with descriptions for all commands.

### Core

| Command | Function |
|---------|----------|
| _(any message)_ | Chat with Claude Code |
| _(voice message)_ | Auto-transcribe (whisper.cpp) + reply (Telegram only) |

### Pipelines (LLM-backed)

| Command | Function |
|---------|----------|
| `/evolve [--dry-run]` | Scan signals, build and auto-install skills |
| `/absorb <url>` | Absorb patterns from any repo |
| `/learn <target>` | Deep-dive with ADOPT/STEAL/SKIP verdicts |
| `/produce [--ideas N]` | Brainstorm business ideas from all signals |
| `/reflect [--days N]` | Self-analysis: patterns, avoidance, next actions |
| `/digest [--days N]` | Morning briefing (sessions, signals, cost) |
| `/gc [--dry-run]` | Garbage collection (stale sessions, orphans) |
| `/wechat [--hours N]` | WeChat group chat digest (reads local DBs) |
| `/discord [--hours N]` | Discord channel digest (from stored messages) |
| `/whatsapp [--hours N]` | WhatsApp group digest (from stored messages) |

### Info

| Command | Function |
|---------|----------|
| `/recall <query>` | Cross-layer search (all 6 memory layers) |
| `/search <query>` | FTS5 search past sessions |
| `/memory` | View MEMORY.md + USER.md |
| `/soul` | View SOUL.md personality |
| `/config` | View config.yaml settings |
| `/skills` | List installed skills (26) |
| `/learnings [query]` | List or search past learnings |
| `/sessions [N]` | List recent sessions |
| `/cost` | Usage and spend |
| `/status` | System overview |
| `/heartbeat` | Quick health check |

### Cron

| Command | Function |
|---------|----------|
| `/loop <interval> <prompt>` | Schedule recurring execution (e.g. `/loop 6h /evolve`) |
| `/loops` | List active cron jobs |
| `/unloop <id>` | Remove a cron job |
| `/pause <id\|--all>` | Pause a cron job |
| `/unpause <id\|--all>` | Resume a cron job |
| `/notify <delay> <msg>` | One-shot delayed notification |

### Admin

| Command | Function |
|---------|----------|
| `/model [name]` | Show or switch model |
| `/autonomy [level]` | Show or set autonomy level (full/supervised/locked) |
| `/new` | Start a new session |
| `/queue` | Show skills pending approval |
| `/approve <name>` | Approve a queued skill |
| `/reject <name>` | Reject a queued skill |

### Telegram-only

| Command | Function |
|---------|----------|
| `/speak <text>` | Text-to-speech (edge-tts, auto-detects language) |
| `/do <instruction>` | Natural language → structured command |
| `/subscribe` | Select channels to monitor for digests |
| `/serve` | Select channels/contacts where the agent responds |
| `/lang [code]` | Set persistent output language |
| `/restart` | Restart gateway remotely |

[All commands →](docs/commands.md)

---

## Architecture

```
User (CLI REPL / Telegram / Discord / WhatsApp / Voice)
  → Gateway (asyncio) or CLI (standalone) → Hook Dispatcher → Session + Cost Gate
  → Auto-Recall (6 layers) → claude -p → SQLite → Git Sync
```

No custom agent loop. Claude Code **is** the runtime — 25+ built-in tools, MCP servers, skills. The gateway adds memory, routing, recall, cron, voice, browser, multi-platform, and safety around it. The CLI REPL (`ae`) bypasses the gateway entirely, calling `claude -p` directly with the same memory, recall, and session infrastructure.

### Key Design Decisions
- **No tool/toolset system** — Claude Code already has tools. We build skills and infrastructure, not abstractions.
- **Bounded memory** — MEMORY.md (2200 chars) + USER.md (1375 chars) + SQLite FTS5. No unbounded growth.
- **Closed-loop** — `auto_approve_skills: true`. Evolve → build → review → install → sync to git. No human gate.
- **Drain-on-shutdown** — In-flight requests complete before restart. No lost work.
- **Modular commands** — 39 Telegram commands split into 9 mixins (admin, pipelines, signals, cron, approval, search, media, misc, subscribe). 32 commands re-implemented for CLI REPL. Adapter core is 630 lines.
- **Dual-layer recall** — FTS5 keyword search + TF-IDF semantic search. Auto-recall injects relevant context before every Claude invocation.
- **Instinct pipeline** — Behavioural patterns observed across sessions are scored, deduplicated, and auto-promoted to MEMORY.md when confidence is high enough.

---

## Voice Pipeline

| Direction | Technology | Latency | Cost |
|-----------|-----------|---------|------|
| **Voice → Text** | Local whisper.cpp (ggml-small multilingual) | ~500ms on Apple Silicon | Free |
| **Text → Voice** | edge-tts (300+ neural voices) | ~1s | Free |
| **Language detection** | CJK heuristic (嘅係唔 → Cantonese, ひらがな → Japanese) | Instant | Free |

Auto-TTS modes: `off` (only `/speak`), `always` (every reply), `inbound` (reply with voice when user sends voice).

---

## Browser Automation

| Browser | When | How |
|---------|------|-----|
| **ABP** (default) | All agent browsing | Bundled Chromium, JS freeze between actions, 90.5% Mind2Web |
| **Brave** | User asks / Cloudflare blocks ABP | CDP on port 9222, isolated profile |
| **Chrome** | User asks / Cloudflare blocks ABP | CDP on port 9223, isolated profile |

Agent profiles are sandboxed at `~/.agenticEvolve/browser-profiles/` — never touches user's real browser data.

---

## Security

| Layer | Tool | When | On Critical |
|-------|------|------|-------------|
| **L1** | `gateway/security.py` | Pre-install: scans raw files | Block + abort pipeline |
| **L2** | AgentShield (1282 tests) | Post-install: scans `~/.claude/` config | Auto-rollback installed skills |

Scans for: credential exfiltration, reverse shells, obfuscated payloads, crypto miners, macOS persistence, prompt injection, npm hook exploits.

---

## Scheduled Cron Jobs

4 autonomous jobs run daily — no human trigger needed.

| Job | Schedule (HKT) | What it does |
|-----|----------------|-------------|
| **evolve-daily** | 6:00 AM | Collects signals from 11 sources: GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChat groups, scores candidates, builds up to 3 new skills, security-reviews, auto-installs, pushes to git |
| **daily-digest** | 8:00 AM | Morning briefing — top signals, skills built, session count, cost summary. Delivered to Telegram |
| **wechat-digest** | 9:00 AM | Daily WeChat group chat digest — summarizes discussions, tools mentioned, key insights from tech groups. Delivered to Telegram |
| **daily-ux-review** | 1:00 AM | Reads the day's conversations, finds friction points, identifies top 3 UX improvements, implements them directly |

Managed via `/loop`, `/loops`, `/unloop`, `/pause`, `/unpause`. Config in `cron/jobs.json`.

---

## Signal Sources (12)

| Source | Collector | API | What it captures |
|--------|-----------|-----|-----------------|
| GitHub Search | `github.sh` | GitHub API (gh CLI) | Trending repos by keyword, starred repo activity, release watch |
| GitHub Trending | `github-trending.py` | GitHub API (gh CLI) | Hot new repos created in the last 7 days |
| Hacker News | `hackernews.sh` | Algolia API | Keyword search + front page + Show HN |
| X / Twitter | `x-search.sh` | Brave Search API | Viral tweets about open source, dev tools, AI |
| Reddit | `reddit.py` | Pullpush.io API | 13 subreddits: LocalLLaMA, programming, ClaudeAI, etc. |
| Product Hunt | `producthunt.py` | RSS/Atom feed | Dev tools + AI product launches |
| Lobste.rs | `lobsters.py` | JSON API | Curated tech news (high signal-to-noise) |
| ArXiv | `arxiv.py` | ArXiv API | Papers from cs.AI, cs.CL, cs.SE, cs.LG |
| HuggingFace | `huggingface.py` | HF API | Trending models and spaces |
| BestOfJS | `bestofjs.py` | Static JSON API | Trending JavaScript/TypeScript projects by daily star growth |
| WeChat | `wechat.py` | Local DB | Group chat messages (reads local data) |
| Discord | `discord.py` | Chromium cache | Cached API responses from desktop app (zero network calls) |

---

## Skills (26 installed)

| Skill | Purpose |
|-------|---------|
| agent-browser-protocol | ABP browser automation via MCP |
| browser-switch | Multi-browser CDP switching (Brave/Chrome) |
| brave-search | Web search via Brave API |
| firecrawl | Web scraping, crawling, search, structured extraction |
| cloudflare-crawl | Free web crawling via Cloudflare Browser Rendering API |
| jshook-messenger | Discord/WeChat/Telegram/Slack interception via jshookmcp MCP |
| wechat-decrypt | Read local WeChat databases and export messages, contacts, groups on macOS |
| session-search | FTS5 session history search |
| cron-manager | Cron job management |
| skill-creator | Official Anthropic skill creation |
| deep-research | Multi-source research pipeline |
| market-research | Market/competitor analysis |
| article-writing | Long-form content creation |
| video-editing | FFmpeg video editing guide |
| security-review | Code security checklist |
| security-scan | AgentShield config scanner |
| autonomous-loops | Self-directed agent loops |
| continuous-learning-v2 | Pattern extraction pipeline |
| eval-harness | Skill evaluation framework |
| claude-agent-sdk-v0.2.74 | Claude Agent SDK patterns |
| nah | Quick rejection/undo |
| unf | Unfold/expand compressed content |
| next-ai-draw-io | Architecture diagrams from natural language |
| mcp-elicitation | Intercept mid-task MCP dialogs for unattended pipelines |
| skill-gap-scan | Diff local skills against community catalog, surface adoption gaps |
| context-optimizer | Auto-compact stale memory files based on `/context` hints |

---

## Recent Changes

### v2.7 — IronClaw Adoption (Phases 1-6)

**Phase 1: Smart Model Routing**
- 13-dimension regex complexity scorer (code patterns, conversation depth, multi-step reasoning, etc.)
- Automatic Sonnet/Opus routing per message — saves $10-20/day on API costs
- Cascade detection: re-invoke with reasoning model if Sonnet shows uncertainty

**Phase 2: Provider Chain**
- Retry → CircuitBreaker → Cache decorator pattern (IronClaw's provider chain architecture)
- Automatic retries with exponential backoff
- Circuit breaker prevents cascade failures
- Response cache for repeated queries

**Phase 3: Security Hardening**
- `credential_guard.py`: LeakDetector scans .env secrets (raw, base64, URL-encoded)
- Two-layer output redaction (credential_guard + redact.py)
- Content sanitizer wired for all platforms (was only WhatsApp before)
- Sandbox deny patterns injected into prompt

**Phase 4: Availability Upgrades**
- Parallel WhatsApp message handling (was serial, now `Semaphore(5)`)
- Event bus (pub/sub) with default triggers (cost alerts, error streaks, reconnect)
- Heartbeat health monitoring with auto-disable notifications
- All 19 hooks now wired (5 were previously dead)

**Phase 5: Memory Upgrades**
- Vector embeddings via sentence-transformers (all-MiniLM-L6-v2, local, no API calls)
- Hybrid search: FTS5 + embedding + RRF fusion ranking
- LLM summarization for context compaction (replaces truncation)
- Memory consolidation: auto-prune MEMORY.md via Sonnet when over limit
- Memory dashboard page with search, stats, embedding status

**Phase 6: Self-Expanding Enhancement**
- SubagentOrchestrator hooks into evolve BUILD stage (observability)
- `skill_metrics` table: track usage, ratings, stale skills
- Background `/learn`: non-blocking execution via BackgroundTaskManager

**Stats:** 822 tests passing (up from ~700). 10 new modules. Estimated savings: $10-20/day from smart routing.

### v2.6 — Security, Observability & Platform Parity
- **Content Sanitizer**: Prompt injection defense with randomized boundary markers, Unicode homoglyph folding (adapted from OpenClaw)
- **Log Redaction**: 17 regex patterns auto-strip API keys, tokens, PEM blocks from all log output
- **Retry Utility**: Exponential backoff + jitter for transient failures, Telegram retry helper
- **Rolling Logs**: RotatingFileHandler (50MB, 5 backups) replaces unbounded log files
- **Tool Loop Detector**: 4-mode detection (generic repeat, poll no-progress, ping-pong, global circuit breaker) prevents runaway sessions
- **Security Self-Audit**: `/doctor` command checks env permissions, config secrets, cost caps, dependencies, sandbox health, DB integrity
- **Diagnostic Event Bus**: Typed events (message, usage, session, loop, heartbeat) with JSONL sink and status summary
- **WhatsApp Commands**: `/cost`, `/status`, `/doctor`, `/help` now work on WhatsApp
- **Voice Pipeline Fixes**: Long audio chunking (48-min → 10-min chunks), OGG→WAV conversion, triple-layer dedup, force reply for voice, 2-part response (transcript + summary)
- **Security Fixes**: Env sanitization in CLI/TUI, dynamic owner paths, content wrapping for served groups

### v2.5 — Security + Intelligence + Plugin System

**Phase 1: Security + Cost Protection**
- Environment variable sanitization — strips 30+ secret patterns from `claude -p` to prevent prompt leaking credentials.
- Per-user sliding-window rate limiting (5/min, 30/hr configurable).
- `[NO_REPLY]` token — agent can skip irrelevant group messages without responding.
- Message debouncing — batches rapid messages (2.5s window, 8s max wait) for served channels.
- `@agent <prompt>` trigger — works for anyone in groups + DMs, with reply-to context and browser MCP.
- Docker sandbox for served chats — isolated Python execution (`--network=none`, `--cap-drop=ALL`, 512MB memory).

**Phase 2: UX + Efficiency**
- Telegram streaming — edit-in-place with 1.5s throttled edits and "..." placeholder.
- Context window management — token estimation, auto-compaction at 60%/85% thresholds.
- Identity linking — `/link` and `/whoami` commands for cross-platform user resolution.

**Phase 3: Intelligence**
- 19-hook plugin system with priority ordering, merge functions, and `has_hooks()` O(1) check. Hook points: `message_received`, `before_invoke`, `llm_output`, `before_model_resolve`, `before_tool_call`, `after_tool_call`, `session_start`, `session_end`, `gateway_start`, `gateway_stop`, `background_task_*`, `before_pipeline_stage`, `after_pipeline_stage`, `subagent_spawned`, `subagent_ended`, `message_sending`, `message_sent`.
- Plugin loader — discovers and loads from `~/.agenticEvolve/plugins/`. Each plugin exports `register(hooks, config)`.
- BackgroundTaskManager — detached long-running tasks with progress tracking. `/tasks` and `/cancel` commands.
- SubagentOrchestrator — generalized multi-Claude execution: `run_parallel`, `run_pipeline`, `run_dag` (dependency graph).

**Phase 4: Polish**
- Gateway exec mode — host execution with 3-tier security (deny/allowlist/full) and configurable approval (off/on-miss/always). 60+ safe bins auto-approved, 13 denylist patterns block dangerous commands (rm -rf, curl|sh, fork bombs, base64 eval).
- Config validation — semantic checks before applying reloaded config. `/reload` command with validation + `config_reload` hook.
- `/allowlist` command to manage exec allowlist (add/rm/clear/list).
- `/hooks` command to inspect registered hook listeners.
- 556 tests total (all passing).

### v2.4 — TUI Commands + Discord Local Cache + WhatsApp File Support

**WhatsApp File & Document Support**
- Users can now send PDF, TXT, CSV, JSON, and other text-based files via WhatsApp. The bridge downloads the file via Baileys `downloadMediaMessage`, saves to `/tmp/agenticEvolve-wa-files/`, and passes the path to Claude Code's Read tool for analysis.
- Also supports audio/voice messages (saved to `/tmp/agenticEvolve-wa-audio/`).
- Supported file types: `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.yaml`, `.html`, `.pdf`, `.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.go`, `.rs`, `.rb`, `.sh`, `.sql`, `.log`, and any plaintext format. Images: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`.
- Files and images auto-escalate to opus model for better analysis.

**WhatsApp Self-Reply Fix**
- Fixed bot replying to its own messages in DMs and served groups (was causing infinite response loops, 18+ replies to one message).
- Bridge.js now checks sender JID against `sock.user.id` — `fromMe` flag is unreliable on Baileys linked devices.
- Python adds 3-second cooldown per chat after sending a reply, plus message ID deduplication.

**Discord Fully Disabled (Zero Network Calls)**
- Discord adapter `start()` is now a complete no-op — no CDP connections, no REST API calls, no token extraction. Account received second community guidelines warning.
- Discord data is read ONLY from local Chromium disk cache (`tools/discord-local/read_cache.py`). Zero network calls to Discord servers.

**TUI Slash Commands**
- 6 new commands in the Textual TUI: `/lang`, `/do`, `/restart`, `/speak`, `/subscribe`, `/serve`. Previously Telegram-only, now fully functional in the CLI.
- Browsable `/subscribe` and `/serve` modal with click-to-toggle targets. Discovers channels from DB subscriptions, platform_messages history, WhatsApp auth files, and Discord Chromium cache.
- `/speak` uses `edge-tts` CLI directly (avoids asyncio conflicts in Textual worker threads).
- `Ctrl+C` copies last assistant response to clipboard via `pbcopy`.
- HelpScreen uses `VerticalScroll` with reordered categories.

**Discord Local Cache Reader**
- Built `tools/discord-local/read_cache.py` — reads Discord messages from the desktop app's Chromium HTTP response cache. Parses gzip-compressed JSON from `~/Library/Application Support/discord/Cache/Cache_Data/`. Zero network calls.
- 5,835 messages across 353 channels recovered from cache, dating back to 2022.
- Added `collectors/discord.py` signal collector for the `/evolve` pipeline, matching the WeChat collector pattern.
- Discord is now a 12th signal source for `/evolve`.

**`/lang` Works Across All Platforms**
- Language preference injection moved from TUI-only to `build_system_prompt()` in `agent.py`. Now works for Telegram, CLI, and any future platform.
- `user_id` parameter threaded through `invoke_claude()` → `build_system_prompt()` → language lookup from `user_prefs` DB.

**Bug Fixes**
- Fixed `/scan-skills` → `/scanskills` — hyphens are invalid in Telegram bot command names, was crashing Telegram adapter startup entirely.
- Fixed Discord poll loop spam — 401 errors now trigger `_auth_failed` flag and stop the poll instead of retrying infinitely.

### v2.3 — CLI REPL + WhatsApp LID Resolution

**Interactive CLI REPL (`ae`)**
- `ae` launches a standalone Rich TUI REPL — no gateway process required. Streaming output with markdown rendering, tool use spinners, and cost tracking.
- 32 slash commands with Tab autocomplete and descriptions. All pipeline commands (`/produce`, `/evolve`, `/learn`, `/absorb`, `/reflect`, `/digest`, `/gc`), info commands (`/memory`, `/soul`, `/config`, `/skills`, `/learnings`, `/recall`, `/search`, `/sessions`), cron management (`/loop`, `/loops`, `/unloop`, `/pause`, `/unpause`, `/notify`), and admin (`/model`, `/autonomy`, `/queue`, `/approve`, `/reject`).
- Session persistence — all messages saved to SQLite with auto-titles. Resume previous sessions with `ae --resume <session_id>`.
- Auto-recall from all 6 memory layers before every invocation. Cost cap enforcement.
- prompt-toolkit input with file-backed history and auto-suggest.

**WhatsApp LID JID Resolution**
- Fixed a critical bug where Baileys v7 delivers DM messages under LID JIDs (`@lid`) instead of phone JIDs (`@s.whatsapp.net`). The bridge now loads `lid-mapping-*_reverse.json` files on startup and resolves LID→phone for incoming messages, outbound sends, and history sync.
- Previously, served contacts like `85254083858` were silently dropped because Python couldn't match the LID JID against phone-based serve targets.

**WhatsApp Serve for DM Contacts**
- `/serve` now supports individual WhatsApp contacts (not just groups). Added `_serve_contacts` set alongside `_serve_groups`. DM routing updated to bypass `allowed_users` for served contacts.

**WhatsApp Media Support**
- Incoming WhatsApp images, documents (PDF, TXT, CSV, etc.), and audio messages are downloaded via Baileys `downloadMediaMessage`, saved to `/tmp/`, and passed to Claude Code for analysis. Messages with media auto-escalate to opus model.

**Auto-Model Escalation**
- Messages containing math, coding, or logic questions are auto-detected via regex and routed to `serve_reasoning_model` (opus) instead of the default `serve_model` (sonnet). Image and file messages also trigger escalation.

**Channel-Specific Knowledge**
- `_CHANNEL_KNOWLEDGE` dict in `run.py` maps channel/group IDs to expert knowledge prompts. Injected after personality prompt for both Discord and WhatsApp served channels. Used for DAMM v2 expertise in degen-damm Discord channel.

### v2.2 — Multi-Platform + Subscribe/Serve

**Multi-Platform Support**
- **Discord desktop adapter** (`gateway/platforms/discord_client.py`) — hooks into the running Discord desktop app via Chrome DevTools Protocol (CDP). Extracts auth token from network requests, then uses Discord REST API for messaging. Supports guild listing, channel listing (with category grouping), DM channels, and message polling.
- **WhatsApp bridge** (`whatsapp-bridge/bridge.js`) — Baileys v7 Node.js bridge communicating via JSON over stdin/stdout. QR code delivery to Telegram for easy linking. LID-to-phone resolution for outbound messages. Group prefix filtering (`/ask`, `@agent`). Contact discovery from auth store lid-mapping files + live message tracking.
- **WeChat** — read-only access via decrypted local SQLCipher databases. Groups and contacts from `contact.db`, messages from `message_0.db`.

**Subscribe & Serve Commands**
- `/subscribe` — Telegram inline keyboard UI to select Discord channels, WhatsApp groups/contacts, or WeChat groups to monitor for digests. Paginated lists (40 per page) with category headers for Discord. WhatsApp split into Groups/Contacts sub-views.
- `/serve` — Same UI to select where the agent actively responds. WhatsApp served groups accept all messages (no prefix required, no allowed_users gate). Serve targets loaded from DB on gateway startup. Dynamic adapter updates when toggling.
- **Subscriptions DB** — `subscriptions` table in session_db with user_id, platform, target_id, target_name, target_type, mode. CRUD functions: `add_subscription`, `remove_subscription`, `get_subscriptions`, `get_serve_targets`, `is_subscribed`.
- **Short ID registry** — Telegram limits `callback_data` to 64 bytes. Long WhatsApp JIDs (`120363427198529523@g.us`) and WeChat chatroom IDs would exceed this. Solution: in-memory numeric ID map (`sub:t:3` instead of `sub:toggle:whatsapp:group:120363...`).

### v2.1 — Modular Architecture + Semantic Recall + Test Harness

**Architecture**
- Split `telegram.py` from 3870 lines into 8 command mixins (`gateway/commands/`): admin, pipelines, signals, cron, approval, search, media, misc. Adapter core reduced to 630 lines.
- Per-user language preferences (`/lang`) persisted to SQLite `user_prefs` table.
- Cross-source signal deduplication in evolve pipeline (URL + title matching).
- Collector retry with 5-second exponential backoff.

**Semantic Search + Instinct Engine**
- TF-IDF cosine similarity search layer augments FTS5 keyword search. `unified_search()` now queries both layers.
- Instinct auto-promotion: high-confidence behavioural patterns (confidence >= 0.8, seen across 2+ projects or 5+ times) auto-promote to MEMORY.md on session cleanup.
- Semantic corpus rebuilt from sessions, learnings, instincts, and memory files. Cached as pickle for fast reload.

**Test Harness — 379 tests (379 pass, 1 xfail)**

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_commands.py` | 81 | All 35+ command handlers: admin, pipelines, signals, cron, approval, search, media, misc + 30 authorization denial tests |
| `test_session_db.py` | 25 | Sessions, messages, FTS5 search, learnings, user prefs, instincts, stats |
| `test_security.py` | 28 | Critical patterns (reverse shell, fork bomb, miners), warnings, prompt injection, safe content, directory scan |
| `test_evolve.py` | 72 | Signal loading, ranking, URL/title dedup, edge cases, collectors, skill approval/rejection, hash verification, queue, reporting |
| `test_agent.py` | 27 | Stderr classification, history compaction (3-pass cascade), title generation, loop detector |
| `test_semantic.py` | 11 | Corpus build (sessions, learnings, instincts), search relevance, caching, score filtering |
| `test_instincts.py` | 8 | Context bug regression, auto-promotion (promote, dedup, char limit) |
| `test_gateway.py` | 10 | Cron parser (every/specific/step/wrap), session key, cost cap |
| `test_voice.py` | 57 | TTS config, language detection, audio format conversion, STT transcription, TTS directives |
| `test_absorb.py` | 49 | Constructor, reporting, scan prompts, security prescan, wechat hours parsing, dry run, AgentShield |
| `test_telegram.py` | 13 | Flag parsing (bool/value/alias/cast), user allowlist |

**Bug Fixes**
- Fixed fork bomb regex in `gateway/security.py` — unescaped `(){}` metacharacters caused the pattern to never match.
- Fixed `upsert_instinct` in `gateway/session_db.py` — SELECT query was missing the `context` column, causing IndexError on repeat upserts with empty context.
- Fixed `_handle_newsession` in `gateway/commands/admin.py` — `set_session_title` (nonexistent function) → `set_title`, and missing `generate_session_id()` caused UNIQUE constraint violations.
- Fixed `_extract_urls` in `gateway/commands/misc.py` — `_URL_RE` class attribute was never defined, causing `AttributeError` on every plain text message.
- Fixed `/restart` spawning duplicate gateway instances — now uses `os.getpid()` to kill only current process.
- Fixed `_extract_urls` crash — `_URL_RE` class attribute was never defined on `MiscMixin`.

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Interface](docs/interface.md) | Usage examples and interaction patterns |
| [Memory](docs/memory.md) | 6-layer memory architecture, auto-recall, instinct scoring |
| [Commands](docs/commands.md) | All 35 commands with flags and examples |
| [Pipelines](docs/pipelines.md) | Evolve, absorb, learn, do, gc pipelines |
| [Skills](docs/skills.md) | Full skill catalog |
| [Security](docs/security.md) | Scanner, autonomy levels, safety gates |
| [Architecture](docs/architecture.md) | Message flow, project structure, design decisions |
| [Roadmap](docs/roadmap.md) | Integration plan — Firecrawl, vision, sandboxing |

---

## Lineage

| Project | Patterns Adopted |
|---------|-----------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Agent runtime — 25+ tools, MCP, skills, subagents |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | Bounded memory, session persistence, messaging gateway, growing status messages |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | Autonomy levels, deny-by-default, hot config reload, risk-tier classification |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 9 skills adapted, AgentShield security, eval-driven development, hook profiles |
| [openclaw](https://github.com/openclaw/openclaw) | Voice pipeline (TTS/STT), browser automation patterns, auto-TTS modes |
| [ABP](https://github.com/theredsix/agent-browser-protocol) | Browser MCP — freeze-between-actions Chromium, 90.5% Mind2Web |
| [deer-flow](https://github.com/bytedance/deer-flow) | Parallel subagent BUILD stage, isolated workspaces per candidate, loop detection, memory queue debounced writes |

---

MIT
