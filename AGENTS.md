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
- BUILD stage creates skills, REVIEW stage validates security/quality/correctness
- When `auto_approve_skills: true` (default), approved skills are auto-installed to `~/.claude/skills/`
- When `auto_approve_skills: false`, skills go to `skills-queue/` and require human `/approve`

### Learn Agent (`/learn`)
- Deep-dives a GitHub repo, URL, or technology
- Analyzes how it benefits Vincent's work (AI agents, onchain infra, dev tools)
- May produce and auto-install a skill to `~/.claude/skills/`
- Updates MEMORY.md with findings

### Cron Agent
- Runs scheduled prompts in fresh sessions (no conversation history)
- Prompts must be self-contained — include all needed context
- Output delivered to the originating platform

## Platform Adapters

| Platform | Adapter | Mode | Notes |
|----------|---------|------|-------|
| Telegram | `gateway/platforms/telegram.py` | Bot API | Primary control plane. All commands, inline keyboards |
| Discord | `gateway/platforms/discord_client.py` | CDP + REST | Hooks desktop app via `--remote-debugging-port=9224`. Token extracted from network requests |
| WhatsApp | `gateway/platforms/whatsapp.py` + `whatsapp-bridge/bridge.js` | Baileys v7 | Node.js bridge over stdin/stdout. QR delivery to Telegram. LID resolution |
| WeChat | Read-only via `collectors/wechat.py` | Decrypted local DBs | No live bridge. Subscribe for digests only |

### Subscribe vs Serve

- **`/subscribe`** — Monitor channels/groups for digests (read-only). Used by `/wechat`, `/discord`, `/whatsapp` digest commands.
- **`/serve`** — Agent actively responds to messages in selected channels/groups. WhatsApp served groups skip `allowed_users` and prefix requirements. Targets persisted in `subscriptions` table, loaded on startup.

## File Conventions

- **Gateway code**: `gateway/` — Python 3.11+, asyncio
- **Platform adapters**: `gateway/platforms/` — each implements `BasePlatformAdapter`
- **Command mixins**: `gateway/commands/` — admin, pipelines, signals, cron, approval, search, media, misc, subscribe
- **Memory**: `memory/MEMORY.md` (2200 char limit), `memory/USER.md` (1375 char limit)
- **Skills queue**: `skills-queue/<name>/SKILL.md` — pending review (only when auto_approve_skills: false)
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

- Skills auto-install when `auto_approve_skills: true` (default). Set to `false` for manual approval gate
- Cost cap enforced before every `claude -p` invocation
- Only whitelisted user IDs can interact with the bot (config.yaml)
- Memory has hard character limits to prevent unbounded growth
- Single gateway instance enforced — kill existing before restart
