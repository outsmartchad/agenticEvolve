agenticEvolve v2 initialized on 2026-03-12. Built on Claude Code as the agent engine.
§
Signal collectors: github.sh (gh CLI), hackernews.sh (Algolia API), x-search.sh (Brave Search). Run as cron jobs.
§
First cycle (v1) found mcp2cli as top signal — 96-99% fewer schema tokens. Skill was rejected for exceeding 100-line limit.
§
HN Algolia API requires HTTPS and URL-encoded operators (%3E not >). HTTP redirects silently fail with curl -s.
§
Claude Code stream-json output requires --verbose flag. Cost data is in the last JSON object as total_cost_usd.
§
2026-03-12 cycle: GitHub trending returned 0 repos (scraper issue). HN returned 50 signals, GitHub releases/starred returned 9/20 via NDJSON format (not JSON array). Signal files are newline-delimited JSON objects, not arrays.
§
2026-03-12 top signals: (1) nah — PreToolUse permission guard, classifies Bash by action type, pip install nah. (2) agent-browser-protocol — forked Chromium MCP, 90.5% Mind2Web, npx -y agent-browser-protocol --mcp. (3) unf — auto file versioning daemon on save, protects against agent accidents pre-commit.
§
Skills created 2026-03-12: nah, agent-browser-protocol, unf.
§
2026-03-13 LEARN scan — everything-claude-code (affaan-m): 4 extractable patterns queued as ecc-hook-patterns skill. (1) Hook profile gating: AE_HOOK_PROFILE=minimal|standard|strict + AE_DISABLED_HOOKS env vars control which hooks fire — wrap all hooks with is_hook_enabled(). (2) Deterministic observation: skills fire ~50-80%, hooks fire 100% — capture every tool event via PreToolUse/PostToolUse to JSONL, analyze async with Haiku; scrub secrets before write. (3) Project-scoped learning: hash git remote URL to 12-char project_id, store observations per project under ~/.ae/homunculus/projects/<id>/; promote patterns to global only when seen in 2+ projects with conf>=0.8. (4) Confidence-weighted instinct YAML format (0.3 tentative → 0.9 near-certain) replaces free-text memory entries; instincts cluster into skills/commands/agents via background agent. Verdict: STEAL — adopt patterns in Python/bash, skip the Node.js plugin machinery.

§
User values proactive systems that notify without being asked; watchdog agent that pushes high-signal notifications unprompted is preferred over pull-based patterns
§
Agent cannot directly send images via Telegram gateway using SendMessage tool; images must be extracted from browser tool_result blocks and forwarded through gateway's image handling
§
When agent hits limitations sending files/images to Telegram, reference similar implementations in other projects (e.g. openclaw) and apply those patterns to the current codebase