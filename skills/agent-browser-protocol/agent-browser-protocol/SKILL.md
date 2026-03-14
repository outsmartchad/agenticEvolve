---
name: agent-browser-protocol
description: Add the Agent Browser Protocol (ABP) MCP server to Claude Code for deterministic browser automation (333+ stars, 90.5% on Online Mind2Web). ABP is a Chromium build that freezes JS between agent actions, returning settled screenshots + structured event logs per step. Use when the user wants to automate browser tasks, scrape dynamic websites, fill web forms, test web UIs, interact with any website reliably, order food, book flights, or do anything in a browser — even if they just say "go to" a URL or "check this website".
argument-hint: [add | demo | remove]
disable-model-invocation: true
allowed-tools: Bash(claude mcp *), Bash(npx *), Bash(curl *)
---

# Agent Browser Protocol (ABP)

A Chromium build with MCP + REST baked directly into the browser engine. ABP reformats web browsing — which is continuous and async — into the discrete, multimodal step format agents reason in.

**90.53% on Online Mind2Web** — the highest published score for browser automation agents.

## Why ABP Exists

Most browser automation stacks force agents to race against a live browser, then patch over timing issues with waits and retries. ABP makes browsing a step machine: each request injects native input, waits for an engine-defined "settled" boundary, captures compositor output (with cursor), returns an event log, then freezes JavaScript until the next step. The agent never reasons from stale state.

## Add to Claude Code

```bash
claude mcp add browser -- npx -y agent-browser-protocol --mcp
```

Then ask Claude to browse any website. If you have a Playwright MCP server configured, disable it first to avoid tool name conflicts.

## What You Get Per Action

Every action returns everything the agent needs for the next decision:
- **Before/after screenshots** (WebP, with virtual cursor)
- **Structured event log** — navigation, dialogs, file choosers, downloads
- **Scroll position** and page dimensions
- **Cursor state** and type
- **Timing data** (~100ms overhead per action)

No need to call "take screenshot" after every action. No need to poll for events.

## Key Capabilities

| Feature | How It Works |
|---------|-------------|
| **Freeze-then-capture** | JS is frozen before screenshot — agent never reasons from stale state |
| **Native input dispatch** | Real input events through Chromium's RenderWidgetHost, not DOM simulation |
| **Element markup** | Request bounding boxes drawn around clickable/typeable elements in screenshots |
| **Virtual cursor** | Compositor-layer cursor appears in screenshots — agent sees what a human would |
| **Dialog handling** | `alert()`, `confirm()`, file choosers surfaced as events with dedicated endpoints |
| **Session recording** | Every action recorded to SQLite — successful sessions become training data |
| **Execution control** | JS + virtual time pause between actions (enabled by default) |

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
4. For element discovery, request markup: `{"screenshot": {"markup": ["clickable", "typeable"]}}`

## REST API (No MCP)

ABP also exposes a full REST API on `localhost:8222`:
```bash
curl -s http://localhost:8222/api/v1/tabs              # list tabs
curl -s -X POST http://localhost:8222/api/v1/tabs/<ID>/navigate \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","screenshot":{"format":"webp"}}'
```

## Browser Selection Rules

**Default: ABP (bundled Chromium)** — use for ALL agent browsing unless the user explicitly asks otherwise.

When the user says "use Brave", "open in Chrome", "use my browser", "with my cookies/login":
1. Launch the requested browser with CDP remote debugging
2. Connect via Playwright CDP or ABP's REST API

```bash
# Launch Brave with CDP
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222 &

# Launch Chrome with CDP  
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9223 &
```

Then connect Playwright to `http://localhost:9222` or `9223`.

**When to use user's browser:**
- User explicitly asks ("use Brave", "use Chrome", "use my browser")
- User needs existing login sessions / cookies
- User wants to see the browser visually

**When to use ABP (default):**
- Everything else — research, scraping, form filling, testing, browsing

## Remove

```bash
claude mcp remove browser
```

Source: https://github.com/theredsix/agent-browser-protocol
