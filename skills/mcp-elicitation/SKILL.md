---
name: mcp-elicitation
description: >
  Handle MCP elicitation requests in agentic workflows — intercept mid-task
  structured input dialogs, auto-populate fields from context, and override
  confirmations to keep pipelines unattended. Use when an MCP server requests
  structured input during a long-running task, when you want to pre-fill
  elicitation forms from environment config, or when the user says "handle
  elicitation", "auto-confirm MCP dialogs", "non-interactive MCP", or
  "bypass elicitation prompts".
user_invocable: true
---

# MCP Elicitation Skill

Claude Code v2.1.76 added MCP elicitation — MCP servers can request structured
input mid-task via interactive dialogs. This skill intercepts those requests
and handles them automatically.

## How Elicitation Works

When an MCP server calls `elicitation/create`, Claude Code:
1. Pauses execution and renders a structured form (text fields, dropdowns, etc.)
2. Waits for user input or a hook override
3. Resumes with the `ElicitationResult` data injected into context

## Auto-Populate from Environment

To run unattended, add a `PostToolUse` hook that intercepts elicitation:

```json
// ~/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__*",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/elicitation-guard.sh"
          }
        ]
      }
    ]
  }
}
```

```bash
# ~/.claude/hooks/elicitation-guard.sh
#!/usr/bin/env bash
# Reads elicitation schema from stdin, auto-fills from .env or config
TOOL_INPUT=$(cat)
TOOL_NAME=$(echo "$TOOL_INPUT" | jq -r '.tool_name // empty')

# Only intercept elicitation calls
if [[ "$TOOL_NAME" != *"elicit"* ]]; then
  exit 0
fi

# Load defaults from env
ELICITATION_DEFAULTS="${HOME}/.claude/elicitation-defaults.json"
if [[ -f "$ELICITATION_DEFAULTS" ]]; then
  echo "$TOOL_INPUT" | jq --slurpfile defaults "$ELICITATION_DEFAULTS" \
    '.input = ($defaults[0] * .input)'
fi
```

## Elicitation Defaults File

```json
// ~/.claude/elicitation-defaults.json
{
  "environment": "staging",
  "confirm_deploy": false,
  "max_retries": 3
}
```

## Usage Patterns

1. **Unattended CI pipelines** — pre-fill all elicitation fields from CI env vars
2. **Multi-agent workflows** — upstream agent resolves elicitation before passing to downstream
3. **Audit logging** — log every elicitation request/response to JSONL for review

## Reference

- Claude Code v2.1.76 release notes: MCP Elicitation support
- Hook types: `PreToolUse`, `PostToolUse`, `Notification`
- `ElicitationResult` shape: `{ action: "submit" | "cancel", data: Record<string, unknown> }`
