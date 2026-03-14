---
name: jshook-messenger
description: Use when the user wants to intercept, monitor, extract, or reverse-engineer messages from Discord, WeChat, Telegram, Slack, or any Electron-based messaging app. Also use for WebSocket monitoring, API capture, JS hooking on web apps, or extracting chat history from desktop apps. Trigger on "intercept discord", "read wechat messages", "monitor websocket", "hook messenger", "extract chats", "reverse engineer app", "capture API traffic".
---

# jshook-messenger — Messaging App Interception via jshookmcp MCP

The `jshook` MCP server is installed and provides 245 tools for browser automation, JS hooking, network interception, WebSocket monitoring, and Electron app reverse engineering. This skill teaches specific workflows for intercepting messages from messaging platforms.

## Pre-flight

The `jshook` MCP server must be running. It auto-starts when you call any `mcp__jshook__*` tool. All tools are prefixed with `mcp__jshook__`.

## Discord Interception

Discord is an Electron app. Messages flow through WebSocket (`wss://gateway.discord.gg`) and REST API (`discord.com/api`).

### Method 1: WebSocket Gateway Monitor (recommended)

Captures ALL real-time messages, presence updates, typing indicators.

```
Step 1: Find and attach to Discord's Chromium process
→ mcp__jshook__electron_inspect_app (path to Discord)

Step 2: Launch browser or attach to Discord's debug port
→ mcp__jshook__browser_attach (wsEndpoint from Discord's CDP)
   OR launch Discord with --remote-debugging-port=9222

Step 3: Enable WebSocket monitoring
→ mcp__jshook__ws_monitor_enable
   This captures all frames on wss://gateway.discord.gg

Step 4: Read captured WebSocket frames
→ mcp__jshook__ws_get_frames
   Filter for opcode 0 (dispatch) events:
   - t: "MESSAGE_CREATE" — new messages
   - t: "MESSAGE_UPDATE" — edited messages
   - t: "MESSAGE_DELETE" — deleted messages
   - t: "TYPING_START" — typing indicators

Step 5: Extract specific channel messages
→ mcp__jshook__ai_hook_generate
   target: { type: "websocket", behavior: "intercept" }
   condition: { urlPattern: "gateway.discord.gg" }
→ mcp__jshook__ai_hook_inject
```

### Method 2: REST API Capture

Captures channel history, user info, server metadata.

```
Step 1: Attach to Discord browser
→ mcp__jshook__browser_attach

Step 2: Enable network monitoring
→ mcp__jshook__network_enable

Step 3: Inject fetch interceptor
→ mcp__jshook__console_inject_fetch_interceptor

Step 4: Navigate Discord / trigger actions
→ mcp__jshook__page_navigate (https://discord.com/channels/...)

Step 5: Extract captured API calls
→ mcp__jshook__network_get_requests
   Filter URL pattern: discord.com/api

Step 6: Get response bodies (message content)
→ mcp__jshook__network_get_response_body (requestId)

Step 7: Extract auth tokens
→ mcp__jshook__network_extract_auth
   Discord uses Bearer token in Authorization header
```

### Method 3: Extract Discord source code

```
→ mcp__jshook__asar_extract (Discord's app.asar)
   macOS: ~/Library/Application Support/discord/app.asar
   Analyze extracted JS for message handling functions
→ mcp__jshook__search_in_scripts (pattern: "MESSAGE_CREATE|handleMessage")
```

## WeChat Interception

### WeChat Desktop (Electron)

```
Step 1: Inspect WeChat Electron structure
→ mcp__jshook__electron_inspect_app (WeChat path)

Step 2: Extract app.asar
→ mcp__jshook__asar_extract

Step 3: Attach and monitor
→ mcp__jshook__browser_attach
→ mcp__jshook__network_enable
→ mcp__jshook__ws_monitor_enable
→ mcp__jshook__console_inject_fetch_interceptor

Step 4: Capture messages
→ mcp__jshook__network_get_requests (filter: wechat|weixin)
→ mcp__jshook__ws_get_frames
```

### WeChat Mini Programs

```
Step 1: Scan for cached mini-program packages
→ mcp__jshook__miniapp_pkg_scan
   Scans default cache directories for .pkg files

Step 2: Unpack target mini-program
→ mcp__jshook__miniapp_pkg_unpack (pkgPath, outputDir)
   Handles WeChat's custom binary format (magic byte 0xBE)

Step 3: Analyze unpacked structure
→ mcp__jshook__miniapp_pkg_analyze (unpackedDir)
   Returns: pages, subPackages, components, appId

Step 4: Search extracted code for API endpoints
→ mcp__jshook__search_in_scripts (pattern: "api|request|wx.request")
```

## Telegram Web Interception

```
Step 1: Launch browser to Telegram Web
→ mcp__jshook__browser_launch
→ mcp__jshook__page_navigate (https://web.telegram.org)

Step 2: Enable all monitoring
→ mcp__jshook__network_enable
→ mcp__jshook__ws_monitor_enable
→ mcp__jshook__console_inject_fetch_interceptor

Step 3: Hook Telegram's message handler
→ mcp__jshook__ai_hook_generate
   target: { type: "function", name: "handleUpdate" }
→ mcp__jshook__ai_hook_inject

Step 4: Extract React/Vue state (Telegram Web K uses Solid.js)
→ mcp__jshook__framework_state_extract

Step 5: Read captured data
→ mcp__jshook__ai_hook_get_data
→ mcp__jshook__ws_get_frames
→ mcp__jshook__network_get_requests
```

## Slack Interception

```
Step 1: Attach to Slack (Electron)
→ mcp__jshook__electron_inspect_app
→ mcp__jshook__browser_attach

Step 2: Monitor WebSocket (Slack uses wss://wss-primary.slack.com)
→ mcp__jshook__ws_monitor_enable

Step 3: Capture REST API
→ mcp__jshook__network_enable
→ mcp__jshook__console_inject_fetch_interceptor
   Filter: slack.com/api

Step 4: Extract messages
→ mcp__jshook__network_get_requests
→ mcp__jshook__ws_get_frames
```

## Generic Web App Interception

For any web-based messaging app:

```
1. mcp__jshook__browser_launch
2. mcp__jshook__page_navigate (app URL)
3. mcp__jshook__network_enable
4. mcp__jshook__ws_monitor_enable
5. mcp__jshook__console_inject_fetch_interceptor
6. mcp__jshook__console_inject_xhr_interceptor
7. [interact with app]
8. mcp__jshook__network_get_requests
9. mcp__jshook__ws_get_frames
10. mcp__jshook__network_export_har (save full capture)
```

## Full API Capture Workflow (one-shot)

jshookmcp has a built-in composite workflow:

```
→ mcp__jshook__web_api_capture_session
   url: "https://discord.com/channels/@me"
   This automatically:
   1. Navigates to URL
   2. Injects fetch + XHR interceptors
   3. Waits for traffic
   4. Extracts auth tokens
   5. Exports as HAR
```

## Anti-Detection

When apps detect automation:

```
→ mcp__jshook__stealth_inject — inject stealth patches
→ mcp__jshook__human_mouse — simulate human mouse movement
→ mcp__jshook__human_typing — simulate human typing speed
→ mcp__jshook__human_scroll — simulate human scrolling
→ mcp__jshook__captcha_detect — detect CAPTCHA challenges
→ mcp__jshook__captcha_vision_solve — solve with vision AI
```

For Camoufox (anti-fingerprint Firefox):
```
→ mcp__jshook__camoufox_server_launch — launch anti-detect browser
   Built-in: OS spoofing, WebRTC blocking, humanized input
```

## Tips

- **Discord tokens**: Found in `Authorization` header of API requests. Also in localStorage key `token`.
- **WeChat**: Desktop uses custom protocol. Mini Programs are easier to intercept.
- **Rate limits**: Don't spam API calls. Use `network_get_requests` to batch-read captured traffic.
- **Export**: Always `network_export_har` to save captures for offline analysis.
- **Electron debug**: Launch any Electron app with `--remote-debugging-port=9222` to enable CDP attachment.
- **Cookie extraction**: `mcp__jshook__page_get_cookies` for session cookies.
- **localStorage**: `mcp__jshook__page_get_local_storage` for tokens stored client-side.

Source: https://github.com/vmoranv/jshookmcp
