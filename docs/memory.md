# Memory Architecture

agenticEvolve maintains 6 memory layers. All layers are searched automatically before every response via `unified_search()`.

## Layers

| Layer | Store | Search | Max Size | Auto-Recalled |
|-------|-------|--------|----------|---------------|
| Sessions | SQLite `messages` table | FTS5 with time-decay scoring | Unbounded | Yes |
| Learnings | SQLite `learnings` table | FTS5 | Unbounded | Yes |
| Instincts | SQLite `instincts` table | FTS5 | Unbounded | Yes |
| Agent Notes | `MEMORY.md` (§-delimited) | Substring (in-memory) | 2,200 chars | Yes |
| User Profile | `USER.md` | Substring (in-memory) | 1,375 chars | Yes |
| Active Session | SQLite `messages` (current sid) | LIKE query | Session lifetime | Yes |

## Auto-Recall

Before every response, `unified_search()` fans out across all 6 layers using the user's message as the query. Results are formatted by `format_recall_context()` and injected into the system prompt as `# Recalled Context`. Cost: ~400-500 extra input tokens per message.

Messages under 15 characters and `/` commands skip auto-recall.

## Sessions

Every conversation is persisted to SQLite with FTS5 full-text indexing. Sessions are grouped by platform + chat ID, with automatic idle timeout (configurable via `session_idle_minutes`). Time-decay scoring ensures recent sessions rank higher — the decay weight halves every 30 days.

When a session ends with 3+ messages, a handoff snapshot is written to `~/.agenticEvolve/sessions/<id>.handoff.json` capturing the last 10 messages for deterministic resumption.

## Learnings

`/learn` and `/absorb` results are stored with structured fields: `target`, `verdict` (ADOPT/STEAL/SKIP), `patterns`, `operational_benefit`, `skill_created`. All fields are FTS5-indexed.

## Instincts

Observations extracted from sessions via `score_and_route_observation()`. Each instinct tracks:

- `pattern` — the observed behavior
- `confidence` — 0.3 to 1.0, incremented on repeat observation
- `seen_count` — how many times observed
- `project_ids` — which projects it appeared in (git remote hash)
- `promoted_to` — null until promoted to skill/command/agent

Scoring heuristics (keyword-based, no LLM):
- Score 5: critical cross-project insight -> instinct + MEMORY.md
- Score 4: strong single-project insight -> instinct (high delta)
- Score 3: useful pattern -> instinct (standard delta)
- Score 2: weak signal -> instinct (low delta)
- Score 1: noise -> discard

Promotion threshold: confidence >= 0.8 across 2+ distinct projects.

## Bounded Notes

`MEMORY.md` (2,200 char limit) and `USER.md` (1,375 char limit) are §-delimited text files injected into every system prompt. High-importance observations (score 4-5) are auto-appended to MEMORY.md via `score_and_route_observation()`.

## Session Consolidation

When a session ends, `consolidate_session()` extracts key patterns from the conversation and routes each through `score_and_route_observation()`. This runs silently — no output to the user.

## Search Functions

| Function | Layer | Method |
|----------|-------|--------|
| `search_sessions(query, limit)` | Sessions | FTS5 + time-decay |
| `search_learnings(query, limit)` | Learnings | FTS5 |
| `search_instincts(query, limit)` | Instincts | FTS5 |
| `search_memory(query)` | MEMORY.md | Substring |
| `search_user_profile(query)` | USER.md | Substring |
| `search_active_session(sid, query)` | Active session | LIKE |
| `unified_search(query, session_id)` | All layers | Fan-out + merge |
| `format_recall_context(results)` | N/A | Formatter for prompt injection |
