# AGENTS.md — agenticEvolve

Project-specific conventions for Claude Code when working inside this codebase.

## Architecture

agenticEvolve is a **gateway + agent engine** system. The gateway (Python asyncio) routes messages from platforms (Telegram, Discord, WhatsApp) to Claude Code (`claude -p`). Claude Code is the agent — we don't build a custom tool-calling loop.

## Agent Roles

When invoked via `claude -p`, the system prompt determines which "role" the agent plays:

### Chat Agent (default)
- Handles regular user messages routed through the gateway
- System prompt: SOUL.md + MEMORY.md + USER.md + session context (last 20 turns)
- Can use all Claude Code tools (terminal, file ops, web, MCP, skills)
- Should proactively save discoveries to MEMORY.md

### Evolve Agent (`/evolve`)
- Orchestrated by `gateway/evolve.py` — 5 stages: COLLECT → ANALYZE → BUILD → REVIEW → REPORT
- Each stage is a separate `claude -p` call with a stage-specific prompt
- BUILD stage creates skills in `~/.agenticEvolve/skills-queue/`, never auto-installs
- REVIEW stage is a separate agent call that validates security, quality, correctness
- Skills require human `/approve` before installation to `~/.claude/skills/`

### Learn Agent (`/learn`)
- Deep-dives a GitHub repo, URL, or technology
- Analyzes how it benefits Vincent's work (AI agents, onchain infra, dev tools)
- May produce a skill in `skills-queue/` (never auto-installed)
- Updates MEMORY.md with findings

### Cron Agent
- Runs scheduled prompts in fresh sessions (no conversation history)
- Prompts must be self-contained — include all needed context
- Output delivered to the originating platform

## File Conventions

- **Gateway code**: `gateway/` — Python 3.11+, asyncio
- **Platform adapters**: `gateway/platforms/` — each implements `BasePlatformAdapter`
- **Memory**: `memory/MEMORY.md` (2200 char limit), `memory/USER.md` (1375 char limit)
- **Skills queue**: `skills-queue/<name>/SKILL.md` — pending human review
- **Installed skills**: `~/.claude/skills/<name>/SKILL.md` — active
- **Cron jobs**: `cron/jobs.json`
- **Config**: `config.yaml` (settings) + `.env` (secrets)
- **Personality**: `SOUL.md`

## Code Style

- Logging: `log = logging.getLogger("agenticEvolve.<module>")`, use structured messages
- Async: gateway and platform adapters are async; `claude -p` calls run in `run_in_executor`
- Error handling: always catch and log, never crash the gateway process
- Telegram rate limits: batch progress messages (every 3 tool calls)
- Subprocess: use `subprocess.Popen` for streaming, `subprocess.run` for simple calls
- Config: access via `gateway/config.py` loader, never read YAML/env directly

## Safety Rules

- Skills NEVER auto-install — always go to `skills-queue/` first
- Cost cap enforced before every `claude -p` invocation
- Only whitelisted user IDs can interact with the bot (config.yaml)
- Memory has hard character limits to prevent unbounded growth
- Single gateway instance enforced — kill existing before restart
