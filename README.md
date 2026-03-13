# agenticEvolve

**A self-evolving personal agent. Learns from the internet. Remembers everything. Runs on Claude Code.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

## The Problem

You use Claude Code at your terminal. But you can't reach it from your phone. You can't reach it while commuting, in meetings, or away from your desk. When you come back, it doesn't remember what you worked on last week. It doesn't know what new tools shipped on GitHub overnight. It doesn't get better over time — every session starts from zero.

## The Fix

agenticEvolve wraps Claude Code in a persistent layer — memory, sessions, and a messaging gateway — so it becomes a personal agent that is always reachable, always learning, and always improving.

- **Text it from Telegram.** Full Claude Code from your phone — write code, debug, refactor, deploy, run terminal commands, search the web. You don't need to be at your desk.
- **It remembers you.** Every conversation is indexed. It maintains notes about your projects, your preferences, your patterns. When you say "remember that auth bug from last Tuesday" — it finds it.
- **It gets smarter while you sleep.** Schedule `/evolve` on cron. It scans GitHub trending and Hacker News, finds tools relevant to your stack, builds Claude Code skills from them, and waits for your approval. Wake up to new capabilities.

---

## See It In Action

```
You:  deploy the staging branch and run the migration
Agent: [pulls branch, runs deploy script, executes migration]
       Deployed. Migration applied — 3 tables updated, 0 errors.

You:  /absorb https://github.com/some-cool-project
Agent: [clones, scans architecture, identifies 4 patterns we're missing]
       Implementing retry logic, health checks, and graceful shutdown.

You:  /evolve
Agent: [scans GitHub trending, HN — scores 12 signals]
       2 skills built: rate-limiter-patterns, structured-logging
       Queued. /approve to install.

You:  what did we work on last week?
Agent: [searches session history]
       3 sessions: JWT auth refactor (Mon), API rate limiting (Wed),
       deploy pipeline fix (Fri). Want details on any?
```

---

## Why Devs and Creators Use This

**Code from anywhere** — Stuck in a meeting and need to push a hotfix? On a train and want to scaffold a new feature? Text the bot. It has full terminal access, file ops, web search, and 16 skills. Your dev environment follows you.

**Never lose context** — Every conversation is saved in SQLite with full-text search. The agent keeps bounded notes about you and your projects in MEMORY.md and USER.md. Context carries across sessions. Ask "what was that regex pattern we used?" and it finds it across weeks of history.

**Autopilot skill growth** — `/evolve` runs a 5-stage pipeline: collect signals from GitHub trending and Hacker News, score them on relevance and novelty, build Claude Code skills from the best ones, validate with a review agent, and queue for your approval. Schedule it daily — you wake up with new capabilities you didn't have to find yourself.

**Absorb any codebase in one command** — `/absorb <repo-url>` clones a repository, maps its architecture, diffs its patterns against your system, identifies what you're missing, and implements the improvements. See a project with great error handling? Absorb it. Found a repo with elegant retry logic? Absorb it.

**Deep research without the tab sprawl** — `/learn <topic>` extracts actionable patterns from any repo or technology. Not a summary — structured findings with three verdicts: ADOPT (use directly), STEAL (take the pattern, skip the dependency), or SKIP. Everything is saved and searchable.

**Set it and forget it** — `/loop every 6h /evolve` runs the evolve pipeline on autopilot. `/notify 30m check deployment` sets reminders. Built-in cron with timezone support. No OS cron dependency. The agent works while you don't.

**Stay safe, stay in control** — Automated security scanner on all external code. Skills require your `/approve` before installation. Daily and weekly cost caps so you never get a surprise bill. Three autonomy levels (full / supervised / readonly). Deny-by-default auth — no one else can use your bot.

---

## Setup

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
```

Configure `~/.agenticEvolve/.env`:
```
TELEGRAM_BOT_TOKEN=<token>
```

Configure `~/.agenticEvolve/config.yaml`:
```yaml
platforms:
  telegram:
    allowed_users: [<user-id>]
```

Run:
```bash
cd ~/.agenticEvolve && python3 -m gateway.run
```

---

## Commands

| Command | What it does |
|---------|-------------|
| _(any text)_ | Chat with Claude Code — code, debug, deploy, research |
| `/evolve` | Scan the internet for signals, build new skills |
| `/absorb <url>` | Learn patterns from any repo, apply them to your system |
| `/learn <topic>` | Deep-dive a repo or technology, extract findings |
| `/memory` | See what the agent remembers about you |
| `/search <query>` | Full-text search across all past conversations |
| `/skills` | List all installed skills |
| `/cost` | Check daily and weekly spend |
| `/loop <interval> <cmd>` | Schedule any command on cron |
| `/approve <name>` | Install a skill from the approval queue |

[All 29 commands ->](docs/commands.md)

---

## Architecture

```
Telegram -> Gateway (asyncio) -> Session + Cost Gate -> System Prompt Assembly -> claude -p -> Stream -> SQLite
```

No custom agent loop. No framework. Claude Code is the agent engine. The gateway handles message routing, memory persistence, session management, cron scheduling, and safety enforcement. [Details ->](docs/architecture.md)

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

- [Commands](docs/commands.md) — all 29 commands
- [Pipelines](docs/pipelines.md) — evolve, absorb, learn, do, gc
- [Skills](docs/skills.md) — 16 installed skills
- [Security](docs/security.md) — scanner, autonomy, safety
- [Architecture](docs/architecture.md) — internals

---

MIT
