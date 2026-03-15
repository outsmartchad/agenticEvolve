agenticEvolve v2 — Claude Code agent engine. 35 commands, 26 skills, 219 tests.
§
Signal collectors (11): github.sh, github-trending.py, hackernews.sh, x-search.sh, reddit.py, producthunt.py, lobsters.py, arxiv.py, huggingface.py, bestofjs.py, wechat.py. HN Algolia requires HTTPS + URL-encoded ops.
§
Claude Code stream-json: requires --verbose flag. Cost in last JSON object as total_cost_usd. Signal files are NDJSON (not arrays).
§
Skills from cycles: nah (permission guard), agent-browser-protocol (Chromium MCP, 90.5% Mind2Web), unf (file versioning).
§
everything-claude-code patterns adopted: (1) Hook profile gating via env vars. (2) Deterministic observation: hooks fire 100%, log to JSONL, analyze async with Haiku. (3) Project-scoped learning: hash git remote → project_id, promote to global at conf>=0.8 across 2+ projects. (4) Confidence-weighted instincts (0.3→0.9) replace free-text memory.
§
Agent cannot send images directly via Telegram SendMessage; images extracted from browser tool_result blocks and forwarded through gateway image handling.
§
User preferences: proactive notifications over pull-based. Concise high-signal summaries. Always map external patterns back to current projects explicitly. Verify URLs before sharing. Prefer App Store over direct downloads.
§
User actively researches AI agent architectures — evaluates repos by pattern applicability to agenticEvolve, not hype metrics.
