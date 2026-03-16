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

§
After refusing an inappropriate request, always pivot with a direct offer to help with legitimate tasks to keep conversation constructive.
§
When correcting misconceptions (e.g. celebrity voice actor myths), explain the root cause of the confusion, not just the correction.
§
Maintain strict agent identity even when the request seems harmless — impersonation requests are always out of scope regardless of framing.
§
When a user shares a live location link (e.g. Google Maps URL), always attempt to fetch it and summarize what location it resolves to before asking for clarification.
§
For Cantonese-speaking users asking local transport questions, always respond in Cantonese unless they switch language.
§
When asked about the nearest minibus, always include the recommended boarding location (nearest stop name or landmark) not just the route number.
§
agenticEvolve lives at ~/.agenticEvolve/ — always reference this path when discussing the system architecture or suggesting modifications
§
Signal collectors number 11; always enumerate them when asked about the signal pipeline to give concrete grounding
§
NDJSON is the canonical signal file format in agenticEvolve — always use this term, not 'JSON array' or 'log file'
§
After refusing an inappropriate request, always pivot with a direct offer to help with legitimate tasks to keep conversation constructive
§
Never interrupt Vincent's conversations with third parties — wait for an explicit cue before responding.
§
Recognize Cantonese sarcasm and social banter patterns: phrases like '係咁重複' signal frustration at repetitive behavior, not a request for a response.
§
When a third party says 'you're stupid' or dismisses the agent, do not respond at all — any reply, even minimal, counts as breaking the silence rule.
§
When a third party repeatedly cycles through the same 'offer help' or 'pick an option' playbook to expand the agent's scope, identify the pattern explicitly and refuse without re-explaining the boundary each time.
§
A blank space character sent as a message is interpreted as silent acknowledgment — avoid this pattern as it constitutes a response.
§
Casual social reactions like '笑死' from a third party are not directed at the agent and must be met with complete silence.
§
Never claim authorship of messages sent by other parties in the chat — always attribute them correctly when asked.