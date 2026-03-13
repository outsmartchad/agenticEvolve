# agenticEvolve

**A personal agent that helps you succeed on the internet. Scans trends, absorbs patterns, builds skills, remembers everything.**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
</p>

---

Persistent agent runtime built on Claude Code (`claude -p`) with a Python asyncio gateway. Exposes full Claude Code capabilities (terminal, file I/O, web search, MCP, 16+ skills) over Telegram. Maintains bounded memory (MEMORY.md + USER.md), SQLite session persistence with FTS5, and a cross-layer auto-recall system that searches 5 memory layers before every response. Includes signal collectors (GitHub trending, Hacker News), a 5-stage skill synthesis pipeline with automated review, and a built-in cron scheduler. Closed-loop — skills are auto-installed after review, new patterns are auto-committed to the repo.

---

## Interface

```
> research the top 5 competitors in the AI code editor space and summarize their pricing
  [searches web, reads pricing pages, compiles data]
  Here's the breakdown: Cursor ($20/mo), Windsurf ($15/mo)...

> /absorb https://github.com/trending-project
  [clones repo, scans architecture, diffs patterns]
  Implemented 3 improvements: retry logic, health checks, graceful shutdown.

> /evolve
  [scans GitHub trending, HN — scores 12 signals]
  2 new skills built and auto-installed: api-rate-limiting, structured-logging

> /learn https://github.com/some-saas-boilerplate
  [deep-dives codebase, extracts patterns]
  ADOPT: their auth flow. STEAL: the webhook retry pattern. SKIP: their ORM choice.
```

---

## Capabilities

- **Build** — Full Claude Code from Telegram. Terminal, file ops, web search, MCP servers, 16+ skills.
- **Research** — Deep-dive any topic, repo, or market. Findings persisted to learnings DB with FTS5 indexing.
- **Create** — Draft articles, threads, documentation. Voice-aware, not generic.
- **Evolve** — 5-stage pipeline: COLLECT (GitHub trending + HN) -> ANALYZE (score relevance/novelty) -> BUILD (synthesize Claude Code skill) -> REVIEW (separate agent validates security + quality) -> AUTO-INSTALL. Schedule on cron for autonomous growth.
- **Absorb** — `/absorb <repo-url>` clones, maps architecture, diffs against self, implements missing patterns. One command to internalize any codebase.
- **Auto-Recall** — Before every response, `unified_search()` fans out across 5 memory layers (sessions FTS, learnings FTS, instincts FTS, MEMORY.md substring, USER.md) and injects relevant context into the system prompt. ~400 extra input tokens per message. The agent retrieves and applies knowledge automatically — no explicit "remember" needed.
- **Reply Context** — All commands resolve reply-to-message context. Reply to a `/learn` summary with `/absorb` to absorb that repo. Reply with `/notify 30m` to set a reminder about that message. Pronouns ("this", "that", "it") resolve to replied message URLs.
- **Cron** — Built-in scheduler with 5-field cron expressions and timezone support. `/loop every 6h /evolve` runs autonomously. No OS cron dependency.
- **Security** — Static analysis scanner (credential exfil, reverse shells, obfuscated payloads, crypto miners). Automated review agent validates skills. Cost caps (daily + weekly). Three autonomy levels (full / supervised / readonly). Deny-by-default auth.

---

## Memory Architecture

```
Layer              Store                   Search Method     Auto-Recalled
-----------        ----------------------  ----------------  -------------
Sessions           SQLite messages table    FTS5              Yes
Learnings          SQLite learnings table   FTS5              Yes
Instincts          SQLite instincts table   FTS5              Yes
Agent Notes        MEMORY.md (2200 chars)   Substring (in-memory) Yes
User Profile       USER.md (1375 chars)     Substring (in-memory) Yes
Active Session     SQLite (current sid)     LIKE query        Yes
```

Instincts are confidence-weighted (0.3-1.0) observations extracted via `score_and_route_observation()`. High-confidence instincts (>= 0.8 across 2+ projects) are eligible for promotion to skills/commands/agents via `get_promotable_instincts()`.

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
| `/evolve` | Scan signals, synthesize and auto-install skills |
| `/absorb <url>` | Absorb patterns from any repo |
| `/learn <target>` | Deep-dive extraction with ADOPT/STEAL/SKIP verdicts |
| `/recall <query>` | Cross-layer search (sessions + learnings + instincts + memory) |
| `/search <query>` | FTS5 search across past sessions |
| `/memory` | View agent memory state |
| `/skills` | List installed skills |
| `/cost` | Usage and spend |
| `/loop <cron> <cmd>` | Schedule recurring execution |
| `/approve <name>` | Install queued skill (when auto_approve_skills: false) |

[All 30 commands ->](docs/commands.md)

---

## Architecture

```
Telegram
  -> Gateway (Python asyncio, single process)
  -> Session lookup + cost cap enforcement
  -> Auto-Recall: unified_search() across 5 memory layers
  -> System prompt: SOUL.md + MEMORY.md + USER.md + recalled context + history (20 turns)
  -> claude -p --model <model> --append-system-prompt <prompt>
  -> Stream-JSON parsing (tool_use events -> progress messages)
  -> Persist: messages to SQLite, observations to instincts, cost to costs table
  -> Auto-sync: git add + commit + push to repo
```

No custom agent loop. No framework. Claude Code is the runtime. The gateway is infrastructure — routing, memory, recall, cron, security, and git sync.

---

## Lineage

| Project | Patterns Adopted |
|---------|-----------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Agent runtime — 25+ tools, MCP, skills, subagents |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | Bounded memory, session persistence, messaging gateway |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | Autonomy levels, deny-by-default, hot config reload |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | Skill patterns, eval-driven development, hook-based observation |

---

## Reference

- [Commands](docs/commands.md) — [Pipelines](docs/pipelines.md) — [Skills](docs/skills.md) — [Security](docs/security.md) — [Architecture](docs/architecture.md)

---

MIT
