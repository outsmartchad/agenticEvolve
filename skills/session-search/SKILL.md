---
name: session-search
description: ALWAYS read this skill when user says "we talked about", "remember when", "what did we decide", "find that session", or references any past conversation or prior discussion.
argument-hint: /session-search "how to deploy"
allowed-tools: Bash(python3 *), Read
---

# Session Search

Search across all past agenticEvolve conversations using SQLite FTS5.

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

4. Summarize the relevant findings concisely.

## Tips

- FTS5 supports prefix queries: `deploy*` matches "deploy", "deployed", "deployment"
- Use quotes for exact phrases: `"cost tracking"`
- Boolean operators: `deploy AND production`, `error NOT warning`
- Column filters are not needed — all content is indexed
