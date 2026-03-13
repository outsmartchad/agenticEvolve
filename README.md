# agenticEvolve

**A personal agent that helps you succeed on the internet. Scans trends, absorbs patterns, builds skills, remembers everything.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

Persistent agent runtime built on `claude -p` with a Python asyncio gateway. 6-layer memory with cross-layer auto-recall on every message. Closed-loop skill synthesis pipeline. Built-in cron. Accessible via Telegram.

---

## Capabilities

| Capability | Description |
|------------|-------------|
| **Build** | Full Claude Code over Telegram — terminal, file I/O, web search, MCP, 16+ skills |
| **Evolve** | 5-stage pipeline: COLLECT -> ANALYZE -> BUILD -> REVIEW -> AUTO-INSTALL. Scans GitHub trending + HN, synthesizes skills, auto-installs after review |
| **Absorb** | `/absorb <url>` — clones repo, maps architecture, diffs patterns, implements improvements |
| **Learn** | `/learn <target>` — deep-dive extraction with ADOPT / STEAL / SKIP verdicts |
| **Auto-Recall** | `unified_search()` across 6 memory layers before every response. ~400 extra tokens/msg |
| **Reply Context** | All commands resolve reply-to-message context. Pronouns ("this", "that") resolve to replied URLs |
| **Cron** | Built-in scheduler. `/loop every 6h /evolve` for autonomous growth |
| **Voice** | `/speak` TTS (edge-tts, 300+ voices). Voice-to-text via local whisper.cpp (~500ms on Apple Silicon). Auto-TTS inbound mode |
| **Browser** | Human-like browser automation (Playwright + CDP). Click, type, screenshot, evaluate |
| **Security** | 2-layer: L1 regex scanner (pre-install) + L2 AgentShield (post-install). Typed failure handling. Deny-by-default |

---

## Setup

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
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
| `/evolve` | Scan signals, build and auto-install skills |
| `/absorb <url>` | Absorb patterns from any repo |
| `/learn <target>` | Deep-dive with ADOPT/STEAL/SKIP |
| `/recall <query>` | Cross-layer search (all 6 memory layers) |
| `/search <query>` | FTS5 search past sessions |
| `/memory` | View agent memory state |
| `/skills` | List installed skills |
| `/cost` | Usage and spend |
| `/speak <text>` | Text-to-speech voice message |
| `/loop <cron> <cmd>` | Schedule recurring execution |
| `/restart` | Restart gateway remotely |
| _(voice message)_ | Auto-transcribe + reply (+ voice if mode=inbound) |

[All 32 commands ->](docs/commands.md)

---

## Architecture

```
Telegram -> Gateway (asyncio) -> Hook Dispatcher -> Session + Cost Gate -> Auto-Recall -> claude -p -> SQLite -> Git Sync
```

No custom agent loop. Claude Code is the runtime. The gateway handles routing, memory, recall, cron, hooks, and safety. Drain-on-shutdown ensures in-flight requests complete before restart.

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Interface](docs/interface.md) | Usage examples and interaction patterns |
| [Memory](docs/memory.md) | 6-layer memory architecture, auto-recall, instinct scoring |
| [Commands](docs/commands.md) | All 32 commands with flags and examples |
| [Pipelines](docs/pipelines.md) | Evolve, absorb, learn, do, gc pipelines |
| [Skills](docs/skills.md) | Installed skill catalog |
| [Security](docs/security.md) | Scanner, autonomy levels, safety gates |
| [Architecture](docs/architecture.md) | Message flow, project structure, design decisions |
| [Roadmap](docs/roadmap.md) | Integration plan — Firecrawl, Cloudflare /crawl, vision, sandboxing |

---

## Lineage

| Project | Patterns Adopted |
|---------|-----------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Agent runtime — 25+ tools, MCP, skills, subagents |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | Bounded memory, session persistence, messaging gateway |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | Autonomy levels, deny-by-default, hot config reload |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | Skill patterns, eval-driven development, hook-based observation |
| [openclaw](https://github.com/openclaw/openclaw) | Voice pipeline, browser automation, TTS/STT patterns |

---

MIT
