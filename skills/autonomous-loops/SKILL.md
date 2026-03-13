---
name: autonomous-loops
description: Patterns and architectures for running Claude Code autonomously in loops — from simple sequential pipelines to multi-agent DAG systems. Use when setting up autonomous development workflows, choosing loop architectures, building CI/CD-style continuous dev pipelines, running parallel agents, or when the user says "run this autonomously", "set up a loop", "automate this workflow", "continuous development", or wants to run multiple Claude instances in parallel.
---

# Autonomous Loops

Patterns for running Claude Code autonomously in loops. Choose the right pattern for the complexity of the task.

## Loop Pattern Spectrum

| Pattern | Complexity | Best For |
|---------|-----------|----------|
| Sequential Pipeline | Low | Daily dev steps, scripted workflows |
| Infinite Agentic Loop | Medium | Parallel content generation, spec-driven work |
| Continuous Claude PR Loop | Medium | Multi-day iterative projects with CI gates |
| De-Sloppify Pattern | Add-on | Quality cleanup after any implement step |
| RFC-Driven DAG | High | Large features, multi-unit parallel work |

## 1. Sequential Pipeline (`claude -p`)

```bash
#!/bin/bash
set -e
claude -p "Read spec. Implement feature with TDD."
claude -p "Review changes. Remove test slop. Run tests."
claude -p "Run build + lint + tests. Fix failures."
claude -p "Create conventional commit."
```

Each step gets fresh context. Order matters. Use `--allowedTools` for restrictions.

**Model routing** — use the right model for the right job:
```bash
claude -p --model opus "Analyze architecture and write plan..."
claude -p "Implement according to plan..."
claude -p --model opus "Review for security and edge cases..."
```

## 2. Infinite Agentic Loop

Two-prompt system: orchestrator parses spec, launches N sub-agents in parallel with unique creative directions.

```
Orchestrator: parse spec -> scan output -> plan iteration -> assign directions -> deploy N agents
Sub-agent: receive context -> follow spec -> generate unique output -> save to output dir
```

Batching: 1-5 simultaneous, 6-20 in batches of 5, infinite in waves of 3-5.

## 3. Continuous Claude PR Loop

Production-grade shell loop: create branch -> run claude -> commit -> push -> create PR -> wait for CI -> auto-fix failures -> merge -> repeat.

Key innovation: `SHARED_TASK_NOTES.md` persists context across iterations.

```bash
continuous-claude --prompt "Add unit tests" --max-runs 10
continuous-claude --prompt "Fix linter errors" --max-cost 5.00
continuous-claude --prompt "Improve coverage" --max-duration 8h
```

## 4. De-Sloppify Pattern

Don't add negative instructions to the implementer. Add a separate cleanup pass:

```bash
claude -p "Implement feature with TDD."
claude -p "Cleanup: remove test slop, over-defensive checks, console.logs. Run tests."
```

Two focused agents > one constrained agent. The implementer creates freely; the cleaner enforces standards.

## 5. RFC-Driven DAG (Ralphinho)

Most sophisticated: decompose RFC into work units with dependency DAG, run each through tiered quality pipeline, land via agent-driven merge queue.

Tiers: trivial (implement->test), small (+review), medium (+research+plan), large (+final review).

Each stage runs in a separate context window — the reviewer never wrote the code it reviews.

## Choosing the Right Pattern

```
Single focused change?           -> Sequential Pipeline
Written spec + parallel needed?  -> RFC-Driven DAG
Written spec + iterative?        -> Continuous Claude PR Loop
Many variations of same thing?   -> Infinite Agentic Loop
Any loop                         -> Add De-Sloppify after implement steps
```

## Anti-Patterns

1. Infinite loops without exit conditions (always set max-runs or max-cost)
2. No context bridge between iterations (use SHARED_TASK_NOTES.md or similar)
3. Retrying same failure without error context
4. Negative instructions instead of cleanup passes
5. All agents in one context window (context pollution)
6. Ignoring file overlap in parallel work (merge conflicts)

## Integration with agenticEvolve

These patterns map directly to our system:
- `/loop` command uses the Sequential Pipeline pattern
- `/evolve` uses a multi-stage pipeline (scan -> analyze -> improve)
- `/absorb` uses the RFC-Driven pattern for breaking down repos
- The De-Sloppify pattern should be applied after any `/do` operation

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) autonomous-loops skill
