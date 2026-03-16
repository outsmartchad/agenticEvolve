---
name: evolve
description: Collect tech signals from GitHub, HN, X, and Discord, score them, and auto-build Claude Code skills from top findings. Trigger manually or via daily cron.
argument-hint: /evolve [--dry-run] [--sources github,hn,x,discord]
allowed-tools: Bash(bash *), Bash(python3 *), Read, Write, WebFetch, mcp__exa__web_search_exa
---

# Evolve

Run the full signal-to-skill pipeline: collect → analyze → build → report.

## Usage

```
/evolve                      # Full cycle: collect all sources, analyze, build skills
/evolve --dry-run            # Collect and analyze only — no skill building
/evolve --sources github,hn  # Run specific collectors only
```

## Step 1 — Collect signals

Run each enabled collector (skip if `--sources` excludes it):

```bash
source ~/.agenticEvolve/config.sh
TODAY=$(date +%Y-%m-%d)
mkdir -p "$SIGNALS/$TODAY"

bash ~/.agenticEvolve/collectors/github.sh
bash ~/.agenticEvolve/collectors/hackernews.sh
bash ~/.agenticEvolve/collectors/x-search.sh
```

Count total: `ls ~/.agenticEvolve/signals/$TODAY/*.json | xargs cat | jq -s 'flatten | length'`

## Step 2 — Analyze signals

Read all JSON files from `~/.agenticEvolve/signals/$TODAY/`. For each signal, score:

- **Relevance** (0–3): Relates to Claude Code, MCP, agent workflows, dev tools, or TypeScript/React?
- **Novelty** (0–3): Check `~/.claude/skills/` — skill doesn't already exist for this?
- **Actionability** (0–3): Can a useful Claude Code skill be built from this in one session?

Total = R + N + A (max 9). Keep top 5 for the report. Flag any with score ≥ 7 as build candidates.

## Step 3 — Build skill (skip if `--dry-run`)

For the highest-scoring signal (score ≥ 7 required):

1. Fetch its README or docs using WebFetch or mcp__exa__web_search_exa
2. Write skill to `~/.agenticEvolve/skills-queue/<skill-name>/SKILL.md`:
   - Must have frontmatter: `name`, `description`, `argument-hint`, `allowed-tools`
   - Must be ≤ 100 lines total
   - No hardcoded secrets — reference env vars only
   - No destructive commands without confirmation guards
3. Validate line count: `wc -l ~/.agenticEvolve/skills-queue/<skill-name>/SKILL.md`
4. If valid, install:
```bash
mkdir -p ~/.claude/skills/<skill-name>
cp ~/.agenticEvolve/skills-queue/<skill-name>/SKILL.md ~/.claude/skills/<skill-name>/SKILL.md
```
5. Log: `echo "$(date '+%Y-%m-%d %H:%M') skill=SKILL_NAME score=SCORE/9 url=URL" >> ~/.agenticEvolve/memory/log.md`

Do NOT overwrite an existing skill in `~/.claude/skills/` — confirm with user first.

## Step 4 — Update action items

For signals scoring 5–6 (promising but not ready to build), append to `~/.agenticEvolve/memory/action-items.md`:
```
- [ ] <title> | <url> | score: X/9 | date: YYYY-MM-DD
```

## Step 5 — Report

Output:
```
## Evolve — YYYY-MM-DD

Signals: N total (GitHub: X | HN: Y | X: Z | Discord: W)

Top findings:
1. [8/9] <title> — <why it matters> — <url>
2. [6/9] ...
3. [5/9] ...

Skill built: `<name>` — <description>
(or: no build — top score X/9 < 7 threshold)
```

## Rules

- Skill names: lowercase-kebab-case, no spaces
- Never exceed 100 lines in a built skill
- Skip build if today's cost already > $3 (check `~/.agenticEvolve/logs/cost.log`)
- If all collectors fail (0 signals), report the failure and stop
