# agenticEvolve

**A self-evolving personal agent. Learns from the internet. Remembers everything. Runs on Claude Code.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

A persistent Claude Code agent accessible via Telegram. Maintains bounded memory across sessions, scans GitHub trending and Hacker News for relevant signals, synthesizes new skills autonomously, and queues them for human approval. No custom agent loop — Claude Code is the runtime.

---

## Interface

```
> deploy the staging branch and run the migration
  [pulls branch, runs deploy script, executes migration]
  Deployed. Migration applied — 3 tables updated, 0 errors.

> /absorb https://github.com/some-cool-project
  [clones, scans architecture, diffs patterns]
  Implementing retry logic, health checks, and graceful shutdown.

> /evolve
  [scans GitHub trending, HN — scores 12 signals]
  2 skills built. Queued. /approve to install.
```

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

## Capabilities

- **Chat** — Full Claude Code from Telegram. Terminal, file ops, web search, MCP, 16 skills.
- **Memory** — SQLite + FTS5 session persistence. Bounded agent notes. Context carries across sessions.
- **Evolve** — Scans GitHub trending + HN, scores signals, builds skills, queues for approval. Schedule on cron for autonomous growth.
- **Absorb** — Deep-scans any repo, diffs patterns against self, implements improvements.
- **Learn** — Extracts actionable patterns from repos or technologies. ADOPT / STEAL / SKIP verdicts.
- **Cron** — Built-in scheduler. `/loop every 6h /evolve` runs pipelines autonomously.
- **Security** — Static analysis on external code. Approval gates. Cost caps. Autonomy levels. Deny-by-default auth.

---

## Commands

| Command | Function |
|---------|----------|
| _(text)_ | Claude Code chat |
| `/evolve` | Scan signals, build skills |
| `/absorb <url>` | Absorb patterns from repo |
| `/learn <target>` | Deep-dive extraction |
| `/memory` | Agent memory state |
| `/search <query>` | FTS5 across all sessions |
| `/skills` | Installed skills |
| `/cost` | Usage and spend |
| `/loop <cron> <cmd>` | Schedule recurring execution |
| `/approve <name>` | Install queued skill |

[All 29 commands ->](docs/commands.md)

---

## Architecture

```
Telegram -> Gateway (asyncio) -> Session + Cost Gate -> claude -p -> Stream -> SQLite
```

[Details ->](docs/architecture.md)

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
