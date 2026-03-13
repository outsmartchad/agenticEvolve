# agenticEvolve

**Claude Code on your phone. It remembers everything. It gets smarter every day.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

Text your Telegram bot. It runs Claude Code — with full terminal access, file operations, web search, and 16 skills — from anywhere. Every conversation is remembered. Every pattern is learned. While you sleep, it scans GitHub trending and Hacker News for tools that match your stack, builds skills from them, and waits for your approval.

No custom agent loop. No framework. Just Claude Code + memory + a messaging gateway.

---

## See It In Action

```
You:     hey, refactor the auth middleware in my express app to use JWT
Bot:     [reads files, edits code, runs tests]
         Done. Replaced session-based auth with JWT in 3 files.
         Tests passing. Here's what changed: ...

You:     /absorb https://github.com/some-cool-project
Bot:     [clones repo, scans architecture, finds 4 patterns we're missing]
         Found 3 improvements. Implementing...
         Done. Added retry logic, health checks, and graceful shutdown.

You:     /evolve
Bot:     [scans GitHub trending, HN, scores 12 signals]
         Built 2 skills: rate-limiter-patterns, structured-logging
         Waiting in queue. /approve to install.
```

That's it. You text, it codes. It learns, you approve.

---

## Get Started (2 minutes)

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
```

Add your Telegram bot token to `~/.agenticEvolve/.env`:
```
TELEGRAM_BOT_TOKEN=your-token-here
```

Add your Telegram user ID to `~/.agenticEvolve/config.yaml`:
```yaml
platforms:
  telegram:
    allowed_users: [your-user-id]
```

Start it:
```bash
cd ~/.agenticEvolve && python3 -m gateway.run
```

Message your bot. Done.

---

## What Can It Do?

**Chat** — Send any message. It goes to Claude Code with full tool access. Ask it to write code, debug, refactor, deploy, research — anything Claude Code can do, but from your phone.

**Remember** — Every conversation is saved in SQLite with full-text search. The agent maintains bounded notes about you and your projects. Context carries across sessions.

**Evolve** — `/evolve` scans GitHub trending + Hacker News for dev signals relevant to your work. Scores them, builds Claude Code skills from the best ones, and queues them for your approval. Run it daily via cron — it gets smarter on autopilot.

**Absorb** — `/absorb <any-repo-url>` deep-scans a repo, compares its patterns against your system, identifies gaps, and implements improvements. One command to learn from any codebase.

**Learn** — `/learn <repo-or-topic>` extracts actionable patterns from any repo or technology. Not a summary — structured findings you can use.

**Schedule** — `/loop every 6h /evolve` and it runs on its own. Built-in cron with timezone support. Set reminders with `/notify`.

**Stay Safe** — Automated security scanner on all external code. Skills require your `/approve`. Daily + weekly cost caps. User whitelisting. Three autonomy levels (full / supervised / readonly).

---

## Key Commands

| Command | What it does |
|---------|-------------|
| Just text it | Chat with Claude Code |
| `/evolve` | Scan internet, build new skills |
| `/absorb <url>` | Learn from any repo |
| `/learn <topic>` | Deep-dive research |
| `/cost` | Check your spend |
| `/memory` | See what the agent remembers |
| `/search <query>` | Search past conversations |
| `/skills` | List installed skills |
| `/loop <interval> <cmd>` | Schedule recurring tasks |
| `/approve <name>` | Install a queued skill |

[All 29 commands ->](docs/commands.md)

---

## How It Works Under The Hood

```
Telegram message
    -> Gateway (Python asyncio)
        -> Session lookup + cost cap check
        -> Build system prompt (personality + memory + history)
        -> claude -p (full Claude Code)
        -> Stream progress back to chat
        -> Save to SQLite
```

No custom agent loop. Claude Code IS the agent. The gateway just routes messages, manages memory, and enforces safety. [Architecture details ->](docs/architecture.md)

---

## Built On

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — the agent engine (25+ built-in tools, MCP, skills, subagents)
- [hermes-agent](https://github.com/NousResearch/hermes-agent) — bounded memory, session persistence, messaging gateway patterns
- [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) — autonomy levels, deny-by-default security
- [everything-claude-code](https://github.com/affaan-m/everything-claude-code) — skills and eval patterns

---

## Docs

- [Commands](docs/commands.md) — all 29 commands
- [Pipelines](docs/pipelines.md) — evolve, absorb, learn, do, gc
- [Skills](docs/skills.md) — 16 installed skills
- [Security](docs/security.md) — scanner, autonomy, safety
- [Architecture](docs/architecture.md) — internals

---

MIT License
