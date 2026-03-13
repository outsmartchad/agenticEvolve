---
name: nah
description: Install and configure nah — a context-aware PreToolUse permission guard for Claude Code (256+ stars). Classifies every tool call by action type using structural analysis in milliseconds, applies allow/ask/block policies, and optionally routes ambiguous cases to an LLM. Use when the user wants to lock down Claude Code permissions, run in allow-all mode safely, guard sensitive files, prevent force pushes, control what tools Claude can use, or audit what Claude has been doing. Also use when discussing Claude Code security, permission management, or safe autonomous operation.
argument-hint: [install | status | config | uninstall | test "<command>"]
disable-model-invocation: true
allowed-tools: Bash(pip *), Bash(nah *)
---

# nah — Context-Aware Permission Guard for Claude Code

`nah` is a PreToolUse hook that classifies every Claude Code tool call by what it actually does — not just which tool is invoked — and applies policies deterministically in milliseconds. No LLM needed for the common case (though optional for ambiguous ones).

The key insight: `rm dist/bundle.js` (inside project, cleanup) and `rm ~/.bashrc` (outside project, destructive) are the same command but completely different actions. nah understands the difference.

## Install

```bash
pip install nah
nah install
```

Then allow-list the tools nah guards in `~/.claude/settings.json`:
```json
{ "permissions": { "allow": ["Bash", "Read", "Glob", "Grep"] } }
```

nah classifies every call and blocks or asks for confirmation on anything dangerous. Do NOT use `--dangerously-skip-permissions` — in bypass mode, hooks fire asynchronously and commands execute before nah can block them.

## Try It Out

```bash
# Live security demo inside Claude Code — 25 cases across 8 threat categories
/nah-demo

# Dry-run any command to see how nah classifies it
nah test "rm -rf /"
nah test --tool Read ~/.ssh/id_rsa
nah test --tool Write ./out.txt
```

## Action Types

nah classifies into 20+ action types. Every type has a default policy:

| Policy | Meaning | Example Types |
|--------|---------|---------------|
| `allow` | Always permit | `filesystem_read`, `git_safe`, `package_run` |
| `context` | Check path/project context | `filesystem_write`, `filesystem_delete`, `network_outbound` |
| `ask` | Always prompt user | `git_history_rewrite`, `lang_exec`, `process_signal` |
| `block` | Always reject | `obfuscated` |

## What It Guards

| Tool | What nah checks |
|------|----------------|
| **Bash** | Structural command classification — action type, pipe composition, shell unwrapping |
| **Read** | Sensitive path detection (`~/.ssh`, `~/.aws`, `.env`, ...) |
| **Write** | Path + project boundary + content inspection (secrets, exfiltration payloads) |
| **Edit** | Path + project boundary + content inspection on replacement string |
| **Glob** | Directory scanning of sensitive locations |
| **Grep** | Credential search patterns outside the project |
| **MCP tools** | Generic classification for third-party tool servers (`mcp__*`) |

## Configure

```yaml
# ~/.config/nah/config.yaml (global)
# .nah.yaml (per-project, can only tighten — never relax)

# Taxonomy profile: full | minimal | none
profile: full

# Override policies for specific action types
actions:
  filesystem_delete: ask
  git_history_rewrite: block
  lang_exec: allow

# Guard sensitive directories
sensitive_paths:
  ~/.kube: ask
  ~/Documents/taxes: block

# Teach nah about your commands
classify:
  database_destructive:
    - "psql -c DROP"
    - "mysql -e DROP"
```

## Optional LLM Layer

For commands the structural classifier can't resolve, nah can consult an LLM:

```yaml
llm:
  enabled: true
  max_decision: ask    # LLM can never escalate past "ask"
  providers: [openrouter]
  openrouter:
    url: https://openrouter.ai/api/v1/chat/completions
    key_env: OPENROUTER_API_KEY
    model: google/gemini-3.1-flash-lite-preview
```

The deterministic layer always runs first. The LLM only resolves leftover "ask" decisions.

## Supply-Chain Safety

Project `.nah.yaml` can add classifications and tighten policies but can never relax them. A malicious repo cannot use `.nah.yaml` to allowlist dangerous commands — only your global config has that power.

## CLI Reference

```bash
nah install / uninstall / update   # lifecycle
nah config show / path             # inspect config
nah test "<command>"               # dry-run classification
nah types                          # list all action types
nah log [--blocks] [--asks]        # recent decisions
nah allow / deny <type>            # adjust policies
nah classify "<cmd>" <type>        # teach custom rules
nah trust <host>                   # trust a network host
nah allow-path <dir>               # exempt a path
nah status                         # show all custom rules
nah forget <type>                  # remove a rule
```

Source: https://github.com/manuelschipper/nah
