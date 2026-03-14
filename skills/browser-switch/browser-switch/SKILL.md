---
name: browser-switch
description: Switch between browsers for browsing tasks. Use when the user says "use Brave", "use Chrome", "open in my browser", "use real browser", "not ABP", or when Cloudflare/bot challenges block ABP. Default is ABP (bundled Chromium). Brave and Chrome connect via Playwright CDP with the user's real cookies/sessions.
---

# Browser Switch

## Default: ABP (Agent Browser Protocol)
The default `browser_*` MCP tools use ABP's bundled Chromium. Best for most tasks.

## When ABP Fails (Cloudflare, bot checks, login-required sites)
ABP freezes virtual time, which breaks Cloudflare challenges. Switch to the user's real browser:

### Launch Brave Browser with CDP
```bash
# Kill any existing Brave debug instance first
pkill -f "Brave Browser.*remote-debugging-port" 2>/dev/null
sleep 1

# IMPORTANT: Use a SEPARATE profile directory to protect user's real browser data.
# NEVER use the user's real profile — it can corrupt extensions, wallets, and cookies.
mkdir -p "$HOME/.agenticEvolve/browser-profiles/brave"

"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --user-data-dir="$HOME/.agenticEvolve/browser-profiles/brave" &

sleep 3
```

### Launch Google Chrome with CDP
```bash
pkill -f "Google Chrome.*remote-debugging-port" 2>/dev/null
sleep 1

# IMPORTANT: Use a SEPARATE profile directory — NEVER the user's real Chrome profile.
mkdir -p "$HOME/.agenticEvolve/browser-profiles/chrome"

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9223 \
  --no-first-run \
  --user-data-dir="$HOME/.agenticEvolve/browser-profiles/chrome" &

sleep 3
```

### CRITICAL SAFETY RULES
- **NEVER** use the user's real browser profile directory
- **NEVER** use `~/Library/Application Support/BraveSoftware/` or `~/Library/Application Support/Google/Chrome/`
- **ALWAYS** use `~/.agenticEvolve/browser-profiles/` for agent browsing
- The agent profile is disposable — no wallets, no extensions, no saved passwords

### Connect and Browse with Playwright
After launching, use Playwright to connect and control the browser:

```bash
# Install playwright if needed
pip3 install playwright 2>/dev/null

python3 << 'PYEOF'
import asyncio
from playwright.async_api import async_playwright

async def browse(url, port=9222):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        context = browser.contexts[0]  # use existing context with cookies
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # Take screenshot
        await page.screenshot(path="/tmp/browser-screenshot.png", full_page=True)
        
        # Get page content
        title = await page.title()
        content = await page.content()
        print(f"Title: {title}")
        print(f"URL: {page.url}")
        print(f"Screenshot saved to /tmp/browser-screenshot.png")
        
        # Don't close — keep browser open for user
        return title, content

asyncio.run(browse("URL_HERE", port=9222))  # 9222=Brave, 9223=Chrome
PYEOF
```

### Navigate Multiple Pages
```python
async def explore_site(base_url, port=9222):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        
        await page.goto(base_url, wait_until="networkidle", timeout=30000)
        
        # Find all links on the page
        links = await page.eval_on_selector_all("a[href]", 
            "els => els.map(e => ({href: e.href, text: e.textContent.trim()})).filter(l => l.href.startsWith(arguments[0]))", 
            base_url)
        
        pages_visited = []
        for i, link in enumerate(links[:10]):  # visit up to 10 pages
            try:
                await page.goto(link["href"], wait_until="networkidle", timeout=15000)
                title = await page.title()
                screenshot_path = f"/tmp/page-{i}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                pages_visited.append({"url": link["href"], "title": title, "screenshot": screenshot_path})
            except:
                pass
        
        return pages_visited
```

## Decision Rules
- **Use ABP** (default): General browsing, research, scraping static sites
- **Use Brave/Chrome**: Cloudflare-protected sites, login-required sites, sites needing real cookies, when user explicitly asks
- **Brave port**: 9222
- **Chrome port**: 9223

## Closing the Debug Browser
```bash
# Close Brave debug instance
pkill -f "Brave Browser.*remote-debugging-port"

# Close Chrome debug instance  
pkill -f "Google Chrome.*remote-debugging-port"
```
