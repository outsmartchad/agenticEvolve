# agenticEvolve

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-16-orange?style=for-the-badge" alt="16 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-29-blue?style=for-the-badge" alt="29 Commands"></a>
</p>

**A personal closed-loop agentic system that evolves your development capabilities daily.** It scans the internet for developer signals, absorbs patterns from any repo, builds skills from what it learns, and gets smarter every session — all through Telegram while you go about your day.

Built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) as the agent engine. Zero custom agent loops. Intelligence lives in prompts, memory, and skills.

<table>
<tr><td><b>Talk to it from anywhere</b></td><td>Telegram, Discord, WhatsApp, CLI — full Claude Code capabilities (file ops, terminal, web search, MCP, 16 skills) from your phone.</td></tr>
<tr><td><b>Closed learning loop</b></td><td>Bounded memory (MEMORY.md + USER.md) + SQLite FTS5 session search. Every conversation is indexed. Every pattern is remembered.</td></tr>
<tr><td><b>Self-evolving</b></td><td>Scans GitHub trending, Hacker News, and X for signals. Auto-builds Claude Code skills with human approval gate. <a href="docs/pipelines.md">See pipelines →</a></td></tr>
<tr><td><b>Absorbs from the wild</b></td><td>Deep-scans any repo, compares against itself, identifies gaps, and implements improvements to its own codebase.</td></tr>
<tr><td><b>Security-first</b></td><td>Automated security scanner, skills approval queue, cost caps, autonomy levels, filesystem scoping, deny-by-default auth. <a href="docs/security.md">See security →</a></td></tr>
<tr><td><b>Cost-controlled</b></td><td>Daily + weekly caps enforced before every Claude invocation. Never wake up to a surprise bill.</td></tr>
</table>

---

## Quick Start

```bash
# Clone
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve

# Symlink the CLI
mkdir -p ~/.local/bin && ln -sf ~/.agenticEvolve/ae ~/.local/bin/ae

# Install dependencies
pip install -r ~/.agenticEvolve/requirements.txt

# Setup
ae setup
```

Then add your Telegram bot token to `~/.agenticEvolve/.env` and your user ID to `config.yaml`. Done.

---

## Usage

```bash
ae gateway              # Start the messaging gateway
ae gateway stop         # Stop it
ae status               # System overview
ae cost                 # Cost breakdown
ae doctor               # Diagnose issues
```

Or just message the bot on Telegram. Regular text goes to Claude Code. Slash commands trigger pipelines.

---

## Core Capabilities

### Pipelines

| Command | What it does |
|---------|-------------|
| `/evolve` | Signal → Skill. Scans trending repos/news, scores relevance, builds skills. |
| `/absorb <target>` | Deep Scan → Self-Improve. Clones a repo, finds gaps, implements improvements. |
| `/learn <target>` | Pattern Extraction. Deep-dives a repo or tech, returns structured findings. |
| `/do <instruction>` | Natural Language → Command. "absorb this repo and skip security" just works. |

All pipelines run in background with streaming progress. All support `--dry-run`.

**[Full pipeline documentation →](docs/pipelines.md)**

### Security

Three autonomy levels (`full` / `supervised` / `readonly`), automated security scanning on all external code, filesystem scoping, forbidden paths, and deny-by-default auth.

**[Full security documentation →](docs/security.md)**

### Commands

29 Telegram commands covering chat, memory, sessions, cost, pipelines, skills, cron, and maintenance.

**[Full command reference →](docs/commands.md)**

### Skills

16 installed skills — 7 original + 9 adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) (73k+ stars). Covers web search, browser automation, research, writing, video editing, security, and more.

**[Full skill catalog →](docs/skills.md)**

---

## Documentation

| Doc | What's covered |
|-----|---------------|
| [Pipelines](docs/pipelines.md) | `/evolve`, `/absorb`, `/learn`, `/do`, `/gc` — full pipeline details |
| [Security](docs/security.md) | Scanner, autonomy levels, filesystem scoping, safety gates |
| [Commands](docs/commands.md) | All 29 Telegram commands with flags |
| [Skills](docs/skills.md) | 16 installed skills, triggering, how to add new ones |
| [Architecture](docs/architecture.md) | Message flow, project structure, design decisions, platform support |
| [Build Plan](BUILD-PLAN-V2.md) | v2 architecture spec (409 lines) |

---

## Inspiration

- [hermes-agent](https://github.com/NousResearch/hermes-agent) — bounded memory, session persistence, messaging gateway, growing-status-message UX
- [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) — autonomy levels, hot config reloading, deny-by-default security
- [everything-claude-code](https://github.com/affaan-m/everything-claude-code) — skills, eval-driven development, continuous learning patterns
- [Anthropic skill-creator](https://github.com/anthropics/claude-plugins-official) — skill creation, eval framework, description optimization

---

## License

MIT
