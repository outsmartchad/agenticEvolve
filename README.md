# agenticEvolve

**A personal agent that helps you succeed on the internet.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

agenticEvolve is a persistent AI agent that lives in your Telegram. It runs Claude Code under the hood — so it can write code, run commands, search the web, read files, and use 16 installed skills. But what makes it different is that it learns. It remembers every conversation. It scans the internet daily for new tools, patterns, and opportunities relevant to your work. It absorbs the best ideas from any codebase you point it at. And it gets better every single day — without you lifting a finger.

Whether you're shipping a product, building an audience, researching competitors, writing content, or automating your workflow — this is your agent.

---

## What It Looks Like

```
> research the top 5 competitors in the AI code editor space and summarize their pricing
  [searches web, reads pricing pages, compiles data]
  Here's the breakdown: Cursor ($20/mo), Windsurf ($15/mo)...

> /absorb https://github.com/trending-project
  [clones repo, scans architecture, finds patterns we're missing]
  Implemented 3 improvements: retry logic, health checks, graceful shutdown.

> /evolve
  [scans GitHub trending, Hacker News — scores 12 signals]
  2 new skills built: api-rate-limiting, structured-logging
  Queued for review. /approve to install.

> write a twitter thread about why developers should use AI agents
  [drafts thread with hook, insights, CTA]
  Done. 8 tweets. Want me to adjust the tone?

> /learn https://github.com/some-saas-boilerplate
  [deep-dives codebase, extracts patterns]
  ADOPT: their auth flow. STEAL: the webhook retry pattern. SKIP: their ORM choice.
```

---

## Capabilities

- **Build** — Write code, debug, refactor, deploy, run terminal commands. Full Claude Code power from your phone.
- **Research** — Deep-dive any topic, repo, or market. Web search, competitor analysis, technology evaluation. Findings are saved and searchable.
- **Create** — Draft articles, threads, newsletters, documentation. Distinctive voice, not AI slop.
- **Evolve** — Scans GitHub trending and Hacker News daily. Finds tools relevant to your stack. Builds new skills. Queues for your approval. Gets smarter on autopilot.
- **Absorb** — Point it at any repo. It clones, analyzes, finds what you're missing, and implements the improvements.
- **Remember** — Every conversation indexed with full-text search. Bounded notes about you and your projects. Context carries across sessions.
- **Automate** — Built-in cron scheduler. `/loop every 6h /evolve` and it runs on its own. Set reminders. Schedule anything.
- **Stay Safe** — Security scanner on all external code. Skills need your approval. Cost caps. Autonomy levels.

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
| _(any message)_ | Chat — code, research, write, automate |
| `/evolve` | Scan the internet, build new skills |
| `/absorb <url>` | Absorb patterns from any repo |
| `/learn <target>` | Deep-dive a repo or topic |
| `/memory` | What the agent knows about you |
| `/search <query>` | Search all past conversations |
| `/skills` | List installed skills |
| `/cost` | Check spend |
| `/loop <interval> <cmd>` | Schedule recurring tasks |
| `/approve <name>` | Install a queued skill |

[All 29 commands ->](docs/commands.md)

---

## Architecture

```
Telegram -> Gateway (asyncio) -> Session + Cost Gate -> claude -p -> Stream -> SQLite
```

No custom agent loop. Claude Code is the agent. The gateway handles routing, memory, sessions, cron, and safety. [Details ->](docs/architecture.md)

---

## Lineage

| Project | Patterns Adopted |
|---------|-----------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Agent runtime — 25+ tools, MCP, skills, subagents |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | Bounded memory, session persistence, messaging gateway |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | Autonomy levels, deny-by-default, hot config reload |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | Skill patterns, eval-driven development |

---

## Reference

- [Commands](docs/commands.md) — [Pipelines](docs/pipelines.md) — [Skills](docs/skills.md) — [Security](docs/security.md) — [Architecture](docs/architecture.md)

---

MIT
