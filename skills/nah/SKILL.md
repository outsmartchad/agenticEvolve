---
name: nah
description: Install and configure nah — a context-aware PreToolUse permission guard for Claude Code that classifies every tool call by action type (filesystem_read, git_history_rewrite, db_write, etc.) and applies allow/ask/block policies. Use when the user wants to lock down Claude Code permissions, run in bypassPermissions mode safely, guard sensitive files, prevent force pushes, or control what tools Claude can use.
argument-hint: [install | status | config | uninstall]
disable-model-invocation: true
allowed-tools: Bash(pip *), Bash(nah *)
---

# nah — Permission Guard for Claude Code

`nah` is a PreToolUse hook that classifies every Claude Code tool call by what it actually does and applies policies deterministically in milliseconds. No LLM needed for classification (though optional for ambiguous cases).

## Install

```bash
pip install nah
nah install
```

This writes a PreToolUse hook into `~/.claude/settings.json`.

## Action Types Classified

| Type | Examples |
|------|---------|
| `filesystem_read` | cat, head, grep |
| `filesystem_write` | write, sed -i, rm |
| `git_history_rewrite` | git rebase -i, git reset --hard, git push --force |
| `package_run` | npm run, npx, pip install |
| `db_write` | INSERT, UPDATE, DELETE |
| `network_egress` | curl, wget |

## Default Policies

- `allow` — safe reads
- `context` — depends on target path/scope
- `ask` — potentially destructive writes
- `block` — git history rewrites, force pushes

## Customize Policies

```bash
nah config          # view current policy config
nah config edit     # open config in editor
```

Policy file is at `~/.nah/config.toml`. Example:

```toml
[policies]
filesystem_write = "ask"
git_history_rewrite = "block"
package_run = "allow"
```

## Uninstall

```bash
nah uninstall
```

## When to Use

Use nah when running Claude Code in `--dangerously-skip-permissions` mode or `bypassPermissions` mode on codebases with sensitive files, live databases, or git history that must not be rewritten.

Source: https://github.com/manuelschipper/nah
