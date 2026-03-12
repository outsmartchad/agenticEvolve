---
name: agent-browser-protocol
description: Add the agent-browser-protocol (ABP) MCP server to Claude Code for synchronized browser automation. ABP forks Chromium to freeze JS/rendering after each action and return fresh state + structured event log. Use when the user wants to automate browser tasks, scrape dynamic websites, fill out web forms, test web UIs, or needs Claude to interact with any website reliably.
argument-hint: [add | demo | remove]
disable-model-invocation: true
allowed-tools: Bash(claude mcp *), Bash(npx *)
---

# agent-browser-protocol (ABP)

A forked Chromium MCP server that keeps the agent synchronized with the browser at every step. After each action it freezes JS execution, captures a screenshot of the frozen state, and returns a structured event log (navigation, file pickers, permission prompts, alerts, downloads).

Scores 90.5% on Online Mind2Web benchmark with Opus 4.6.

## Add to Claude Code

```bash
claude mcp add browser -- npx -y agent-browser-protocol --mcp
```

## Key Behaviors

- **Freeze-then-capture**: After click/type/scroll, JS is frozen before screenshot — agent never reasons from stale state.
- **Event log**: Each action returns structured events (e.g., `{type: "navigation", url: "..."}`, `{type: "download_started"}`).
- **Multimodal loop**: Screenshot + event log = full context per step.

## Common Failures ABP Eliminates

- Modal appearing after last screenshot blocks next input
- Dynamic filters cause reflow between steps
- Autocomplete dropdown covers target element
- `alert()` / `confirm()` interrupting flow
- Downloads triggering with no reliable completion signal

## Usage Pattern

When using ABP in an agent loop:

1. Call `browser_navigate` or `browser_click` / `browser_type`
2. Read the returned screenshot + event log
3. Decide next action based on frozen current state — not a guess

## Remove

```bash
claude mcp remove browser
```

Source: https://github.com/theredsix/agent-browser-protocol
