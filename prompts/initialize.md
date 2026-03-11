You are the agenticEvolve initializer. This runs ONCE to set up the system.

## Your task

Set up the agenticEvolve environment at ~/.agenticEvolve/. The directory structure already exists. You need to populate the memory files with sensible defaults.

## Steps

1. Read ~/.agenticEvolve/config.sh to confirm it exists and has defaults.

2. Write ~/.agenticEvolve/memory/watchlist.md with:

```markdown
# Watchlist

## GitHub Accounts
- anthropics
- openai
- snarktank
- openclaw
- nicepkg
- AnandChowdhary

## X Accounts
- @AnthropicAI
- @OpenAI
- @alexalbert__
- @aabordes
- @kaboroevich

## Keywords
- claude code
- mcp server
- agent loop
- agentic workflow
- harness engineering
- dev tools ai
- claude skills
- agent harness
- coding agent

## HN Filters
- Show HN + keyword matches
- Points > 30
```

3. Write ~/.agenticEvolve/memory/state.md with:

```markdown
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

## System Notes
- Initialized on: (today's date)
- Collectors: github.sh, hackernews.sh, x-search.sh
```

4. Write ~/.agenticEvolve/memory/log.md with:

```markdown
# Log

Append-only. Never edit. Never truncate (GC archives old entries).

---
```

5. Write ~/.agenticEvolve/memory/action-items.md with:

```markdown
# Action Items

<!-- Format: - [ ] description | source: x | signal: date | priority: N -->
<!-- Grep for "- [ ]" to find pending items. "- [x]" = done. -->
```

6. Touch ~/.agenticEvolve/logs/cost.log if it doesn't exist.

7. Verify each collector script is executable:
   - chmod +x ~/.agenticEvolve/collectors/github.sh
   - chmod +x ~/.agenticEvolve/collectors/hackernews.sh
   - chmod +x ~/.agenticEvolve/collectors/x-search.sh

8. Run a quick test of each collector to validate APIs work:
   - Run github.sh and check output
   - Run hackernews.sh and check output
   - Run x-search.sh and check output (may skip if BRAVE_API_KEY not set)

9. Report what was set up and any issues.

10. Output `<promise>INITIALIZED</promise>` on success.

## Rules
- Do NOT modify collector scripts — just verify they work
- Do NOT install any packages
- Write files exactly as shown above
- If a file already exists with content, do NOT overwrite — skip it and report
