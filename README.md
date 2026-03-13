# agenticEvolve

**A self-evolving personal agent. Learns from the internet. Remembers everything. Runs on Claude Code.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

A persistent agent that connects to you via Telegram. It runs Claude Code with full terminal, file ops, web search, and 16 installed skills. Every session is indexed. Memory is bounded and self-maintained. Signal collectors scan GitHub trending and Hacker News on a cron cycle, score relevance, and synthesize new skills autonomously — pending human approval.

No custom agent loop. No framework. Claude Code is the runtime. This is the infrastructure around it.

---

## Interface

```
> refactor the auth middleware to use JWT
  [reads files, edits 3 modules, runs tests]
  Done. Session-based auth replaced with JWT. Tests passing.

> /absorb https://github.com/some-cool-project
  [clones, scans architecture, identifies 4 missing patterns]
  Implementing 3 improvements: retry logic, health checks, graceful shutdown.

> /evolve
  [scans GitHub trending, HN — scores 12 signals]
  2 skills built: rate-limiter-patterns, structured-logging
  Queued. /approve to install.
```

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

## Capabilities

**Chat** — Any message routes directly to Claude Code with full tool access — terminal, file operations, web search, MCP servers, and 16 installed skills. Write code, debug, refactor, deploy, research. Anything Claude Code can do, accessible from Telegram.

**Memory** — Every conversation is persisted in SQLite with FTS5 full-text search. The agent maintains bounded notes about you (USER.md) and its own discoveries (MEMORY.md). Context carries across sessions automatically. Nothing is forgotten. Search any past session with `/search`.

**Evolve** — `/evolve` triggers a 5-stage pipeline: signal collectors scan GitHub trending and Hacker News, score each signal on relevance and novelty, build Claude Code skills from the highest-scoring candidates, run a separate review agent for quality validation, and queue results for human approval. Schedule it on cron — the agent gets smarter on autopilot.

**Absorb** — `/absorb <repo-url>` deep-scans any repository. Clones it, maps its architecture, diffs its patterns against this system, identifies gaps, and implements improvements directly into the codebase. One command to internalize the best patterns from any project.

**Learn** — `/learn <repo-or-topic>` extracts actionable patterns from any repository or technology. Not a summary — structured findings with three verdicts: ADOPT (use directly), STEAL (take the pattern, skip the dependency), or SKIP. Findings persist in the learnings database, searchable via `/learnings`.

**Schedule** — Built-in cron scheduler with 5-field expressions and timezone support. `/loop every 6h /evolve` runs the evolve pipeline autonomously. `/notify 30m check deployment` sets one-shot reminders. All scheduled jobs run inside the gateway process — no OS cron dependency.

**Security** — Automated static analysis on all external code before processing. Detects credential exfiltration, reverse shells, obfuscated payloads, malicious install hooks, and crypto miners. Three autonomy levels (full / supervised / readonly) control tool access. Skills require human `/approve` before installation. Daily and weekly cost caps enforced before every Claude invocation. Deny-by-default auth on all platforms.

---

## Commands

| Command | Function |
|---------|----------|
| _(text)_ | Claude Code chat |
| `/evolve` | Scan signals, synthesize skills |
| `/absorb <url>` | Absorb patterns from repo |
| `/learn <target>` | Deep-dive extraction |
| `/memory` | View agent memory state |
| `/search <query>` | FTS5 search across all sessions |
| `/skills` | List installed skills |
| `/cost` | Usage and spend |
| `/loop <cron> <cmd>` | Schedule recurring execution |
| `/approve <name>` | Install queued skill |

[Full command reference (29 commands) ->](docs/commands.md)

---

## Architecture

```
Telegram -> Gateway (asyncio) -> Session + Cost Gate -> System Prompt Assembly -> claude -p -> Stream -> SQLite
```

No orchestration layer. Claude Code is the agent. The gateway handles routing, memory, sessions, cron, and safety enforcement. [Details ->](docs/architecture.md)

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

- [Commands](docs/commands.md)
- [Pipelines](docs/pipelines.md)
- [Skills](docs/skills.md)
- [Security](docs/security.md)
- [Architecture](docs/architecture.md)

---

MIT
