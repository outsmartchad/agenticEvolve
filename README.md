# agenticEvolve

**A self-evolving AI agent — grows itself daily.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-26-orange?style=for-the-badge" alt="26 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-35-blue?style=for-the-badge" alt="35 Commands"></a>
</p>

**[简体中文](README.zh.md)** | **[繁體中文](README.zh-TW.md)** | **[日本語](README.ja.md)**

---

Persistent agent runtime built on `claude -p` with a Python asyncio gateway. 6-layer memory + cross-layer auto-recall. Closed-loop skill synthesis. Voice I/O. Browser automation. Built-in cron. 2-layer security. 35 Telegram commands — your entire dev machine in your pocket.

---

## What can you do with it?

**Browse the web for you**
> "Go to the Anthropic docs and find the latest Claude model pricing." The agent opens ABP browser, navigates, extracts the data, and sends you a clean summary. If Cloudflare blocks it, it auto-switches to Brave.

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
| **Build** | Full Claude Code over Telegram — terminal, file I/O, web search, MCP, 26 skills |
| **Evolve** | 5-stage pipeline: COLLECT → ANALYZE → BUILD → REVIEW → AUTO-INSTALL. Scans 11 sources: GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChat groups, synthesizes skills |
| **Absorb** | `/absorb <url>` — clones repo, maps architecture, diffs patterns, implements improvements into your system |
| **Learn** | `/learn <target>` — deep-dive extraction with ADOPT / ADAPT / SKIP verdicts |
| **Voice** | Send voice messages → local whisper.cpp transcription (~500ms). `/speak` → edge-tts with 300+ voices. Auto-detects Cantonese/Mandarin/Japanese/Korean |
| **Browser** | ABP (Agent Browser Protocol) for default browsing. Auto-switches to Brave/Chrome via CDP when Cloudflare blocks. Isolated agent profiles |
| **Auto-Recall** | `unified_search()` across 6 memory layers before every response (~400 tokens/msg) |
| **Cron** | `/loop every 6h /evolve` — autonomous growth on a schedule |
| **Security** | L1: regex scanner pre-install (reverse shells, credential theft, crypto miners). L2: AgentShield post-install (1282 tests, 102 rules). Auto-rollback on critical findings |
| **Hooks** | Typed async event system — `message_received`, `before_invoke`, `llm_output`, `tool_call`, `session_start`, `session_end` |
| **Resilience** | Drain-on-shutdown (30s wait for in-flight requests). Typed failure classification (auth/billing/rate-limit). 3-pass context compaction. Hot config reload. Loop detection (warn@3 identical turns, terminate@5). Memory queue read-through (debounced atomic writes, no stale reads). Parallel BUILD stage (ThreadPoolExecutor, 3 isolated workspaces) |

---

## Setup

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
brew install whisper-cpp ffmpeg  # voice support
```

```bash
# ~/.agenticEvolve/.env
TELEGRAM_BOT_TOKEN=<token>
```

```yaml
# ~/.agenticEvolve/config.yaml
platforms:
  telegram:
    allowed_users: [<user-id>]
```

```bash
cd ~/.agenticEvolve && python3 -m gateway.run
```

---

## Commands

| Command | Function |
|---------|----------|
| _(any message)_ | Chat with Claude Code |
| _(voice message)_ | Auto-transcribe (whisper.cpp) + reply (+ voice if mode=inbound) |
| `/evolve` | Scan signals, build and auto-install skills |
| `/absorb <url>` | Absorb patterns from any repo |
| `/learn <target>` | Deep-dive with verdicts |
| `/speak <text>` | Text-to-speech (auto-detects language) |
| `/recall <query>` | Cross-layer search (all 6 memory layers) |
| `/search <query>` | FTS5 search past sessions |
| `/do <instruction>` | Natural language → structured command |
| `/loop <cron> <cmd>` | Schedule recurring execution |
| `/memory` | View agent memory state |
| `/skills` | List installed skills (26) |
| `/cost` | Usage and spend |
| `/wechat [--hours N]` | WeChat group chat digest (简体中文) |
| `/produce [--ideas N]` | Brainstorm business ideas from all signals |
| `/digest` | Morning briefing |
| `/restart` | Restart gateway remotely |

[All 35 commands →](docs/commands.md)

---

## Architecture

```
User (Telegram/Voice) → Gateway (asyncio) → Hook Dispatcher → Session + Cost Gate
  → Auto-Recall (6 layers) → claude -p → SQLite → Git Sync
```

No custom agent loop. Claude Code **is** the runtime — 25+ built-in tools, MCP servers, skills. The gateway adds memory, routing, recall, cron, voice, browser, and safety around it.

### Key Design Decisions
- **No tool/toolset system** — Claude Code already has tools. We build skills and infrastructure, not abstractions.
- **Bounded memory** — MEMORY.md (2200 chars) + USER.md (1375 chars) + SQLite FTS5. No unbounded growth.
- **Closed-loop** — `auto_approve_skills: true`. Evolve → build → review → install → sync to git. No human gate.
- **Drain-on-shutdown** — In-flight requests complete before restart. No lost work.

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

## Signal Sources (11)

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
