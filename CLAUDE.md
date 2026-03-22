# agenticEvolve

## Rules
Agent roles and architecture: @AGENTS.md

## Browser — Use Playwright MCP, NOT ABP
ALWAYS use Playwright MCP tools for any browser interaction. NEVER use the built-in browser (ABP).

Available tools:
- `mcp__playwright__browser_navigate` — go to a URL
- `mcp__playwright__browser_snapshot` — get page content (accessibility tree, NOT raw HTML)
- `mcp__playwright__browser_click` — click elements by ref number from snapshot
- `mcp__playwright__browser_fill_form` — fill input fields
- `mcp__playwright__browser_take_screenshot` — capture screenshots
- `mcp__playwright__browser_evaluate` — run JavaScript on the page
- `mcp__playwright__browser_wait_for` — wait for elements/network idle
- `mcp__playwright__browser_press_key` — keyboard input
- `mcp__playwright__browser_tabs` — manage browser tabs
- `mcp__playwright__browser_close` — close browser

### Workflow:
1. `browser_navigate` to the URL
2. `browser_snapshot` to read the page (returns accessibility tree with ref numbers)
3. Use ref numbers from snapshot to `browser_click` or `browser_fill_form`
4. `browser_snapshot` again to see the result

### Do NOT:
- Use `WebFetch` for pages that need JavaScript rendering
- Use the built-in ABP browser
- Try to parse raw HTML — use `browser_snapshot` which gives structured content
