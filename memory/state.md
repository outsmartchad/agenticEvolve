# State

What agenticEvolve knows. Read this FIRST every cycle.

## Signal Sources
- GitHub trending repos with >20 stars in 24h have highest actionable signal
- HN "Show HN" posts often contain new tools worth building skills for
- Anthropic engineering blog posts frequently introduce new Claude Code features
- X posts from @AnthropicAI and @alexalbert__ often preview upcoming features

## Lessons
- Start with GitHub + HN + X collectors (simplest, no auth needed)
- Brave Search with site:x.com is sufficient for X signal collection
- Skills that wrap API integrations (like brave-search) are the most reusable
- Always validate API keys exist before attempting to build API-dependent skills

## Key Findings
- mcp2cli pattern: turning MCP servers into CLIs saves 96-99% schema tokens; skills that shell out to CLIs are leaner than injecting tool schemas
- Claude Code v2.1.71+ ships native `/loop` and cron tools; build skills that compose on top rather than reimplementing
- openclaw v2026.3.7 introduced ContextEngine plugin interface — potential for custom compaction/context strategies

## System Notes
- Initialized on: 2026-03-11
- Collectors: github.sh, hackernews.sh, x-search.sh
