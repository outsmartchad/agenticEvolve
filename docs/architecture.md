# Architecture

## How It Works

Each incoming message flows through this pipeline:

1. **Gateway** receives message from Telegram/Discord/WhatsApp
2. **Session manager** resolves or creates a session (idle timeout = 2h)
3. **Cost cap** checked before invoking Claude (daily + weekly)
4. **Conversation history** loaded from current session (last 20 turns, 8K chars)
5. **System prompt** assembled from SOUL.md + MEMORY.md + USER.md + autonomy rules
6. **Claude Code** (`claude -p`) processes the message with full tool access
7. **Streaming progress** — tool use events batched and sent as growing status message
8. **Response** sent back to the platform
9. **Message + response** persisted to SQLite for future search

The cron scheduler runs inside the gateway process, ticking every 60s to execute due jobs.

---

## Project Structure

```
~/.agenticEvolve/
├── ae                          # CLI entrypoint
├── config.yaml                 # Settings (model, platforms, cost caps, autonomy)
├── .env                        # Secrets (bot tokens)
├── SOUL.md                     # Agent personality
├── AGENTS.md                   # Project conventions + agent roles
│
├── gateway/                    # Messaging gateway (~5,000 lines Python)
│   ├── run.py                  # GatewayRunner — main process, cron scheduler
│   ├── agent.py                # Claude Code invocation wrapper
│   ├── evolve.py               # 5-stage evolve pipeline
│   ├── absorb.py               # 5-stage absorb pipeline
│   ├── autonomy.py             # Autonomy levels, risk tiers, filesystem scoping
│   ├── security.py             # Security scanner
│   ├── gc.py                   # Garbage collection
│   ├── config.py               # Config loader (YAML + .env, hot-reload)
│   ├── session_db.py           # SQLite + FTS5 (sessions, learnings, costs)
│   └── platforms/
│       ├── base.py             # Platform adapter interface
│       ├── telegram.py         # Telegram (~2,300 lines, 39 commands)
│       ├── discord_client.py   # Discord (CDP + local cache, serve disabled)
│       └── whatsapp.py         # WhatsApp (Baileys v7 bridge, live)
│
├── memory/
│   ├── MEMORY.md               # Agent's notes (2200 char limit)
│   ├── USER.md                 # User profile (1375 char limit)
│   └── sessions.db             # SQLite + FTS5
│
├── cron/jobs.json              # Scheduled jobs
├── skills-queue/               # Skills pending human approval
├── collectors/                 # Signal collectors (github.sh, hackernews.sh, x-search.sh, discord.py, wechat.py)
├── tools/
│   ├── discord-local/          # Chromium disk cache reader for Discord messages
│   │   └── read_cache.py       # Parses gzip-compressed API responses from cache
│   └── wechat-decrypt/         # WeChat SQLCipher DB decryption pipeline
├── whatsapp-bridge/bridge.js   # Node.js WhatsApp bridge
└── logs/                       # gateway.log, cost.log
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Claude Code is the agent engine** | No custom agent loop. `claude -p` has 25+ tools, MCP, skills, subagent delegation. We build infrastructure around it. |
| **Bounded memory** | MEMORY.md (2200 chars) + USER.md (1375 chars). Frozen snapshot pattern — injected at session start, never changes mid-session. |
| **Session continuity** | Last 20 turns (8K chars) fed back into each `claude -p` call. Sessions auto-expire after 2h idle. |
| **Skills follow skill-creator standards** | Pushy descriptions, progressive disclosure, proper frontmatter. Heavy docs go in `references/`. |
| **Safety gates everywhere** | Security scanner, skills queue, cost caps, user whitelisting, deny-by-default auth, bounded memory. |
| **Cron inside the gateway** | No OS cron dependency. 5-field cron expressions with timezone support. |
| **Hot config reloading** | `config.py` tracks mtime, reloads on change. No restart needed. |
| **Growing status message** | One Telegram message edited in-place every 3s with accumulated tool lines. No spam. |

---

## Platform Support

| Platform | Status | Library | Data Source |
|----------|--------|---------|-------------|
| Telegram | Working (39 commands) | python-telegram-bot | Bot API (live) |
| Discord | Fully disabled (local cache only) | None (no network) | Chromium disk cache (zero API calls) |
| WhatsApp | Working (serve + subscribe) | Baileys v7 (Node.js bridge) | Live bridge over stdin/stdout |
| WeChat | Read-only (digests) | Local SQLCipher DBs | Decrypted local databases |
