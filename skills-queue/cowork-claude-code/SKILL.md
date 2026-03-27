---
name: cowork-claude-code
description: Set up and use Anthropic's Cowork feature — Claude Code for collaborative, multi-user async workflows. Use when the user says "set up cowork", "share claude code session", "async claude collaboration", "cowork preview", or wants to run Claude Code workflows across a team without real-time coordination.
user-invocable: true
version: 1.0.0
source: https://claude.com/blog/cowork-research-preview (HN: 1298pts, 2026-03-28 evolve cycle)
---

# Cowork: Claude Code for Collaborative Workflows

Cowork is Anthropic's research preview that extends Claude Code into async multi-user collaboration — shared context, handoffs, and parallel agent tasks across team members.

## When to Use

- User wants to share a Claude Code session or hand off work to a teammate
- Running async Claude Code pipelines across distributed contributors
- Delegating subtasks to other agents or users in an organized workspace
- Evaluating whether Cowork fits agenticEvolve multi-agent architecture

## Quick Setup

```bash
# Requires Claude Code >= latest and valid subscription
# Access via claude.com/cowork (research preview)
claude cowork init           # initialize shared workspace
claude cowork invite <email> # invite collaborators
claude cowork session list   # list active sessions
```

## Key Features (Research Preview)

| Feature | Description |
|---|---|
| Shared context | Multiple users see the same codebase state |
| Async handoffs | Pause and resume tasks across users/agents |
| Task delegation | Assign subtasks to specific agents or humans |
| Audit trail | Full history of who did what and when |

## Integration with agenticEvolve

Cowork can serve as the coordination layer for multi-agent evolve cycles:

```yaml
# config.yaml addition
cowork:
  enabled: false           # set true when preview access granted
  workspace_id: ""         # from claude.com/cowork dashboard
  auto_delegate: false     # auto-delegate BUILD stage to Cowork agents
```

## Evaluation Checklist

- [ ] Confirm research preview access at claude.com/cowork
- [ ] Test single shared workspace with 2 Claude Code instances
- [ ] Benchmark latency on async handoff (target: < 5s)
- [ ] Verify context isolation between users
- [ ] Assess fit for agenticEvolve BUILD → REVIEW stage handoff

## Rules

- Cowork is a research preview — do not use for production workflows until GA
- Never share workspace credentials or workspace_id in public repos
- Always verify preview access before guiding setup steps
