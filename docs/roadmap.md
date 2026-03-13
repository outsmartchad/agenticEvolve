# Roadmap

Integration plan for new capabilities. Ordered by impact/effort ratio.

## P0 — High Impact, Low Effort

### Firecrawl CLI + Skill
- Install `firecrawl-cli` globally, set `FIRECRAWL_API_KEY` in env
- Build a skill teaching the agent when/how to use `firecrawl` commands
- Commands available: `firecrawl scrape`, `firecrawl crawl`, `firecrawl search`, `firecrawl map`, `firecrawl agent`, `firecrawl browser`
- Upgrades `/evolve` (better signal collection via `firecrawl search`), `/absorb` (crawl entire doc sites), `/learn` (clean scrape any page), general chat (web research via `firecrawl agent`)
- No MCP server needed — CLI is callable directly from `claude -p` via Bash
- Install: `npx -y firecrawl-cli@latest init --all --browser`
- Free tier: 500 credits. Hobby: $16/mo (3k credits)
- Source: https://docs.firecrawl.dev/sdks/cli

### Cloudflare /crawl Skill
- Build a skill that calls Cloudflare Browser Rendering REST API
- Use for bulk crawling in `/evolve` signal collection as a free fallback
- Free tier: 5 crawls/day, 100 pages/crawl, 10 min browser/day. Paid: $0.09/hr, 100k pages
- AI extraction built-in (Workers AI or BYO model)
- Sitemap-aware, robots.txt compliant, R2 caching
- MCP option: `@cloudflare/playwright-mcp` for interactive browser automation
- Source: https://developers.cloudflare.com/browser-rendering/rest-api/crawl/

## P1 — Quick Wins

### Vision (Image Analysis)
- Claude Code already reads images natively via the Read tool
- Wire Telegram photo handler (`_handle_photo`) to send images to `claude -p`
- Use cases: screenshot analysis, diagram understanding, OCR, UI inspection
- Cost: ~$0.004 per 1MP image (~400 extra input tokens)
- Effort: Low — already built into Claude, just need to pipe photos through

### Edge TTS (Text-to-Speech)
- Add `/speak` command — convert agent response to voice message in Telegram
- `pip install edge-tts` — free, 300+ neural voices, 40+ languages
- Telegram voice messages use Opus/OGG format (need MP3 -> OGG conversion)
- Risk: unofficial Microsoft API, could break
- Effort: Low — `pip install` + ~30 lines of code
- Source: https://github.com/rany2/edge-tts

## P2 — Infrastructure

### Docker Sandbox
- Run `/absorb` and `/evolve` in isolated Docker containers
- Prevent absorbed code from touching the host filesystem
- Build image with Claude CLI pre-installed
- Effort: Medium — Dockerfile + orchestration
- Cost: Free (your own infra)
- Best for: <5 concurrent agents on a single server

## P3 — Future / Scale

### E2B (Sandboxed Execution)
- Agent-focused Firecracker microVMs, <500ms startup
- Used by Perplexity, Manus, Hugging Face
- SDK: `sandbox.commands.run('claude -p "..."')`
- Hobby: free ($100 credit). Pro: $150/mo
- Best for: multi-tenant isolation, productionizing
- Source: https://e2b.dev

### Daytona (Dev Environments)
- 61.5k stars, <90ms sandbox creation, open-source
- Snapshots (save/resume state), stateful, multi-region
- $200 free compute included
- Best for: long-running stateful agents, computer-use scenarios
- Source: https://daytona.io

### ElevenLabs / OpenAI TTS
- Upgrade from Edge TTS when we need reliability or commercial compliance
- ElevenLabs: best quality, $5-99/mo, startup grant available
- OpenAI TTS: $15/1M chars, outputs Opus directly (Telegram native)
- Source: https://elevenlabs.io, https://platform.openai.com/docs/guides/text-to-speech

### Container Backend Abstraction
- Abstract Docker/E2B/Daytona behind a common interface
- Config toggle: `sandbox.backend: docker | e2b | daytona`
- Per-pipeline sandbox policy (e.g. `/absorb` always sandboxed, chat runs local)

## Status

| Item | Priority | Status |
|------|----------|--------|
| Firecrawl CLI + Skill | P0 | Planned |
| Cloudflare /crawl Skill | P0 | Planned |
| Vision (photo handler) | P1 | Planned |
| Edge TTS / `/speak` | P1 | Planned |
| Docker Sandbox | P2 | Planned |
| E2B | P3 | Planned |
| Daytona | P3 | Planned |
| ElevenLabs / OpenAI TTS | P3 | Planned |
| Container Abstraction | P3 | Planned |
