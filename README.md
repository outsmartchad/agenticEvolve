# agenticEvolve

**A personal closed-loop agentic system that evolves your development capabilities daily.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-18-orange?style=for-the-badge" alt="18 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-32-blue?style=for-the-badge" alt="32 Commands"></a>
</p>

---

Persistent agent runtime built on `claude -p` with a Python asyncio gateway. 6-layer memory with cross-layer auto-recall. Closed-loop skill synthesis. Voice I/O. Browser automation. Built-in cron. 2-layer security. Accessible via Telegram — your entire dev machine in your pocket.

---

## Capabilities

| Capability | Description |
|------------|-------------|
| **Build** | Full Claude Code over Telegram — terminal, file I/O, web search, MCP, 18 skills |
| **Evolve** | 5-stage pipeline: COLLECT → ANALYZE → BUILD → REVIEW → AUTO-INSTALL. Scans GitHub trending + HN, synthesizes skills |
| **Absorb** | `/absorb <url>` — clones repo, maps architecture, diffs patterns, implements improvements into your system |
| **Learn** | `/learn <target>` — deep-dive extraction with ADOPT / ADAPT / SKIP verdicts |
| **Voice** | Send voice messages → local whisper.cpp transcription (~500ms). `/speak` → edge-tts with 300+ voices. Auto-detects Cantonese/Mandarin/Japanese/Korean |
| **Browser** | ABP (Agent Browser Protocol) for default browsing. Auto-switches to Brave/Chrome via CDP when Cloudflare blocks. Isolated agent profiles |
| **Auto-Recall** | `unified_search()` across 6 memory layers before every response (~400 tokens/msg) |
| **Cron** | `/loop every 6h /evolve` — autonomous growth on a schedule |
| **Security** | L1: regex scanner pre-install (reverse shells, credential theft, crypto miners). L2: AgentShield post-install (1282 tests, 102 rules). Auto-rollback on critical findings |
| **Hooks** | Typed async event system — `message_received`, `before_invoke`, `llm_output`, `tool_call`, `session_start`, `session_end` |
| **Resilience** | Drain-on-shutdown (30s wait for in-flight requests). Typed failure classification (auth/billing/rate-limit). 3-pass context compaction. Hot config reload |

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
| `/skills` | List installed skills (18) |
| `/cost` | Usage and spend |
| `/restart` | Restart gateway remotely |

[All 32 commands →](docs/commands.md)

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

## Skills (18 installed)

| Skill | Purpose |
|-------|---------|
| agent-browser-protocol | ABP browser automation via MCP |
| browser-switch | Multi-browser CDP switching (Brave/Chrome) |
| brave-search | Web search via Brave API |
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

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Interface](docs/interface.md) | Usage examples and interaction patterns |
| [Memory](docs/memory.md) | 6-layer memory architecture, auto-recall, instinct scoring |
| [Commands](docs/commands.md) | All 32 commands with flags and examples |
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

---

MIT
