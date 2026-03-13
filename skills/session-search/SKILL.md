---
name: session-search
description: Search past agenticEvolve conversations using SQLite FTS5. ALWAYS use this skill when the user says "we talked about", "remember when", "what did we decide", "find that session", "last time", "earlier today", "previous conversation", or references any past discussion, prior context, or historical decision — even if they don't explicitly say "search".
argument-hint: /session-search "how to deploy"
allowed-tools: Bash(python3 *), Read
---

# Session Search

Search across all past agenticEvolve conversations using SQLite FTS5. This gives you recall over every session, decision, and discussion — the agent's long-term episodic memory.

## Usage

```
/session-search <query>
```

## Procedure

1. Run the search:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.agenticEvolve')
from gateway.session_db import search_sessions
import json
results = search_sessions('YOUR_QUERY_HERE', limit=5)
print(json.dumps(results, indent=2))
"
```

2. Parse the results. Each result contains:
   - `session_id` — unique session identifier
   - `source` — platform (telegram, discord, whatsapp, cli)
   - `title` — human-readable title (if set)
   - `started_at` — when the session began
   - `matches` — list of matching messages with role, content preview, and timestamp

3. If the user needs more detail from a specific session, fetch the full transcript:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.agenticEvolve')
from gateway.session_db import get_session_messages
import json
msgs = get_session_messages('SESSION_ID_HERE')
print(json.dumps(msgs, indent=2))
"
```

4. Summarize the relevant findings concisely. Lead with the answer, then cite the session.

## Query Tips

FTS5 is powerful — use it:
- Prefix queries: `deploy*` matches "deploy", "deployed", "deployment"
- Exact phrases: `"cost tracking"`
- Boolean operators: `deploy AND production`, `error NOT warning`
- Combine for precision: `"daily evolve" AND cron`

## Why This Matters

Without session search, every conversation starts from zero. This skill gives the agent continuity — it can reference what was decided, what was tried, and what worked. That's the difference between a tool and a partner.
