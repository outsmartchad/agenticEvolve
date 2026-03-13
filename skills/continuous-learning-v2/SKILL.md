---
name: continuous-learning-v2
description: Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence scoring, and evolves them into skills/commands/agents. Use when setting up automatic pattern extraction, configuring instinct-based learning, tuning confidence thresholds, evolving instincts into reusable skills, or when the user says "learn from this", "extract patterns", "what have you learned", "improve yourself", or wants the agent to get smarter over time.
version: 2.1.0
---

# Continuous Learning v2.1 — Instinct-Based Architecture

Turn Claude Code sessions into reusable knowledge through atomic "instincts" — small learned behaviors with confidence scoring. The idea: every session teaches the agent something, and those lessons should accumulate and compound.

## The Instinct Model

```yaml
---
id: prefer-functional-style
trigger: "when writing new functions"
confidence: 0.7
domain: "code-style"
scope: project
project_id: "a1b2c3d4e5f6"
---
# Prefer Functional Style
## Action
Use functional patterns over classes when appropriate.
## Evidence
- Observed 5 instances of functional pattern preference
- User corrected class-based approach to functional
```

Properties: atomic, confidence-weighted (0.3-0.9), domain-tagged, evidence-backed, scope-aware (project/global).

## How It Works

```
Session Activity -> Hooks capture tool use (100% reliable)
  -> observations.jsonl (per-project)
  -> Observer agent (background, Haiku) detects patterns
  -> Creates/updates instincts with confidence scores
  -> /evolve clusters instincts into skills/commands/agents
```

The key insight from v1: skills fire ~50-80% of the time (model decides). Hooks fire 100% deterministically — every tool call is captured, no patterns missed.

## Setup: Observation Hooks

Add to `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"}]}]
  }
}
```

## Project Scoping (v2.1)

Auto-detects project via git remote URL -> 12-char hash. Same repo on different machines gets same project ID.

| Pattern Type | Scope | Examples |
|-------------|-------|---------|
| Language/framework conventions | project | "Use React hooks", "Django REST patterns" |
| Security practices | global | "Validate input", "Sanitize SQL" |
| Tool workflow preferences | global | "Grep before Edit", "Read before Write" |

## Confidence Scoring

| Score | Meaning |
|-------|---------|
| 0.3 | Tentative — suggested but not enforced |
| 0.5 | Moderate — applied when relevant |
| 0.7 | Strong — auto-approved |
| 0.9 | Near-certain — core behavior |

Increases when: pattern repeatedly observed, user doesn't correct.
Decreases when: user explicitly corrects, contradicting evidence appears.

## Promotion (Project -> Global)

Auto-promotion criteria: same instinct in 2+ projects, average confidence >= 0.8.

## Commands

| Command | Description |
|---------|-------------|
| `/instinct-status` | Show instincts with confidence |
| `/evolve` | Cluster instincts into skills/commands |
| `/instinct-export` | Export instincts for sharing |
| `/instinct-import` | Import from others |
| `/promote` | Promote project -> global |
| `/projects` | List projects and instinct counts |

## File Structure

```
~/.claude/homunculus/
├── identity.json
├── projects.json
├── instincts/personal/      # Global instincts
├── evolved/                  # Global skills/commands/agents
└── projects/<hash>/
    ├── observations.jsonl
    ├── instincts/personal/   # Project-scoped
    └── evolved/
```

## Integration with agenticEvolve

Our `/evolve` command already implements a version of this pattern — scanning the codebase, extracting patterns, and creating skills. The instinct system adds the confidence layer: patterns that keep appearing get promoted, patterns that get corrected fade.

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) continuous-learning-v2 skill
