# agenticEvolve Upgrade Plan — IronClaw Patterns Adoption

> Generated: 2026-03-18
> Goal: Close gaps in Security (5→9), Availability (7→9), Memory (6→8), maintain Self-Expanding lead (8→9)
> Constraint: Every change must benefit a **personal AI agent product**, not enterprise infra

---

## Phase 1: Smart Model Routing (Session 1)

**ROI: Highest — saves $10-20/day immediately**

### What
13-dimension regex complexity scorer that routes messages to Sonnet (cheap) or Opus (expensive) per-message instead of per-channel.

### Why it fits
We burn $12-33/day. 60-70% of messages are simple (greetings, short questions, status checks). These don't need Opus. A personal agent should be cost-aware — money saved = longer runway.

### Build

**New file: `gateway/smart_router.py` (~300 lines)**

```
SmartRouter
├── score_complexity(text: str) → int (0-100)
│   13 dimensions, weighted sum:
│   ├── reasoning_words (0.14) — "analyze", "explain", "prove", "compare", "optimize"
│   ├── token_estimate (0.12) — (char_count - 20) / 5, capped 100
│   ├── code_indicators (0.10) — backticks, function/class/import/def, file paths
│   ├── multi_step (0.10) — "step by step", "first...then", numbered lists, "plan"
│   ├── domain_specific (0.10) — solidity, defi, MEV, blockchain, trading, onchain
│   ├── creativity (0.07) — "design", "create", "imagine", "brainstorm", "invent"
│   ├── question_complexity (0.07) — question marks × 20, open-ended patterns × 25
│   ├── precision (0.06) — "exact", "specific", math symbols, "calculate"
│   ├── context_dependency (0.05) — "above", "previous", "earlier", vague pronouns
│   ├── ambiguity (0.05) — hedging language, "maybe", "not sure", "possibly"
│   ├── tool_likelihood (0.05) — "run", "execute", "check", "search", "find"
│   ├── sentence_complexity (0.05) — commas, semicolons × 2, conjunctions
│   └── safety_sensitivity (0.04) — "production", "deploy", "delete", "security", "mainnet"
│
│   Multi-dimensional boost:
│   ├── 3+ dimensions > 20 → total × 1.3
│   └── 2 dimensions > 20 → total × 1.15
│
├── classify(text: str) → Tier
│   Priority order:
│   1. Explicit hints: [tier:opus], [tier:sonnet] in message
│   2. Pattern overrides: greetings/thanks → Flash, security audit → Frontier
│   3. Score-based: 0-15 Flash, 16-40 Standard, 41-65 Pro, 66+ Frontier
│
├── select_model(text: str, config: dict) → str
│   ├── Flash/Standard → config["serve_model"] (Sonnet)
│   ├── Pro → Sonnet, with cascade flag
│   └── Frontier → config["serve_reasoning_model"] (Opus)
│
└── CascadeDetector
    After Sonnet responds, scan for uncertainty:
    ├── "I'm not sure", "I cannot determine", "this requires more analysis"
    ├── "I don't have enough", "beyond my capabilities"
    └── If detected → re-invoke with Opus, return that response instead
```

### Wire into
- `gateway/run.py:handle_message()` — before model selection at ~line 470
- Replace static `model = config["model"]` with `model = smart_router.select_model(text, config)`
- Cascade: after getting response, if tier was Pro and response is uncertain, re-invoke

### Config
```yaml
smart_routing:
  enabled: true
  cascade_enabled: true
  domain_keywords: [solidity, defi, MEV, onchain, ERC, uniswap]
```

### Observability
- Atomic counters: sonnet_count, opus_count, cascade_count, cascade_hit_count
- Expose in `/api/status` → dashboard overview shows routing breakdown
- Log: `INFO Smart router: score=42 tier=Pro model=sonnet cascade=false`

### Dashboard
- Add "Model Routing" card to overview: pie chart of Sonnet vs Opus usage
- Add "Estimated Savings" metric: (opus_price - sonnet_price) × sonnet_count

### Tests (~30)
- Each dimension scores correctly for known inputs
- Tier classification at boundaries (15, 40, 65)
- Explicit hint override works
- Pattern overrides (greetings → Flash)
- Multi-dimensional boost triggers correctly
- Cascade detection catches uncertainty phrases
- Tool calls always route to primary (if we keep that rule)
- Empty/short messages → Flash

---

## Phase 2: Provider Chain (Session 2)

**ROI: Medium — reliability, caching saves repeated costs**

### What
Decorator pattern wrapping Claude invocations: Retry → SmartRouting → CircuitBreaker → Cache.

### Why it fits
A personal agent needs to be reliable. If Anthropic has a blip, the agent shouldn't crash — it should retry. If you ask the same question twice in an hour, don't burn tokens again. The chain also gives one clean integration point for all invocation concerns.

### Build

**New file: `gateway/provider_chain.py` (~350 lines)**

```
Provider (Protocol)
├── invoke(prompt, model, session_context, ...) → {text, cost, input_tokens, output_tokens}

RetryProvider(inner: Provider)
├── max_retries: 3 (config)
├── Backoff: 1s × 2^attempt ± 25% jitter, floor 100ms
├── Retryable: subprocess failures, HTTP 429/500/502/503, timeout
├── NOT retried: context too long, auth failure, cost limit exceeded
├── Respects Retry-After header from retry.py
└── Wraps: inner.invoke()

CircuitBreakerProvider(inner: Provider)
├── States: Closed → Open → HalfOpen → Closed
├── threshold: 5 consecutive failures → Open
├── recovery_timeout: 30s → transitions to HalfOpen
├── half_open_successes: 2 → transitions to Closed
├── Open state: immediate reject with clear error ("Claude API circuit open, retry in Xs")
├── Tracks only transient errors (not auth/config failures)
└── Wraps: inner.invoke()

ResponseCache(inner: Provider)
├── key: SHA-256(model + messages_json + system_prompt_hash)
│   NOTE: system_prompt changes per session (memory recall), so hash it, don't include raw
├── ttl: 1 hour (config)
├── max_entries: 200 (config, LRU eviction)
├── NEVER cache: tool-heavy responses, responses with file edits, cost > $0.50
├── Stats: hit_count, miss_count, log hit rate every 100 requests
└── Wraps: inner.invoke()

Composition at startup (run.py):
    raw = agent.invoke_claude  # or invoke_claude_streaming
    chain = RetryProvider(
        SmartRoutingProvider(  # Phase 1
            CircuitBreakerProvider(
                ResponseCache(raw)
            )
        )
    )
```

### Why no Failover
We only have one LLM provider (Anthropic via Claude CLI). Failover makes sense when you have OpenAI as backup. Not our case. Skip.

### Wire into
- `gateway/agent.py` — replace direct `invoke_claude`/`invoke_claude_streaming` calls in run.py with `provider_chain.invoke()`
- The chain wraps the existing invoke functions, doesn't replace their internals

### Config
```yaml
provider_chain:
  retry:
    max_retries: 3
    base_delay_ms: 1000
  circuit_breaker:
    threshold: 5
    recovery_secs: 30
  cache:
    enabled: true
    ttl_secs: 3600
    max_entries: 200
```

### Tests (~35)
- Retry: exponential backoff timing, jitter range, non-retryable errors pass through
- Circuit breaker: state transitions (closed→open→halfopen→closed)
- Cache: hit/miss, TTL expiry, LRU eviction, tool-heavy exclusion
- Full chain: composition order, error propagation

---

## Phase 3: Security Hardening (Session 3)

**ROI: Critical for product credibility — closes biggest gap**

### What
Wire the 4 existing unwired security modules + add output redaction + add leak detection.

### Why it fits
A personal agent handles your API keys, credentials, private messages. If it leaks a token in a Telegram group, game over. Security isn't optional for a product people trust with their digital lives.

### Sub-tasks

#### 3a. Wire content_sanitizer into ALL external input paths

Currently only WhatsApp served groups. Missing: Telegram, cron, /learn, /absorb, web content.

**Changes:**
- `gateway/platforms/telegram.py` — wrap served group messages with `wrap_external_content()`
- `gateway/run.py` — wrap `/learn` and `/absorb` URL content
- `gateway/run.py` — wrap cron job output before feeding to Claude
- `gateway/run.py` — wrap channel knowledge injection

**Effort:** Small — just import and call at 4-5 injection points.

#### 3b. Wire exec_allowlist into agent invocation path

The module is complete but `evaluate()` is never called. The challenge: Claude Code runs as a subprocess with `--dangerously-skip-permissions`. We can't intercept individual Bash tool calls.

**Pragmatic approach:** Instead of intercepting tool calls (impossible without modifying Claude Code):
1. Add a **post-invocation audit** — after Claude responds, scan the stream-json output for Bash tool calls that executed
2. Log any commands that would have been denied by exec_allowlist
3. For served groups (untrusted users): add `exec_allowlist.evaluate()` check to the sandbox prompt — tell Claude which commands are allowed/denied
4. Future: when Claude Code supports pre-exec hooks, wire evaluate() as a blocking check

**Changes:**
- `gateway/agent.py` — after invoke, parse tool_calls from stream-json, run evaluate() on Bash commands, log violations
- `gateway/sandbox.py:build_sandbox_prompt()` — inject allowlist rules into the prompt

#### 3c. Redact agent output before sending to users

Currently `redact.py` only filters logs. Agent responses to Telegram/WhatsApp are unredacted.

**Changes:**
- `gateway/run.py` — after getting response_text, run `redact(response_text)` before sending
- This catches: if Claude reads .env and outputs a token, it gets masked before reaching the user

**Effort:** 2 lines of code. Highest ROI security fix.

#### 3d. Build credential_guard.py — leak detection on output

New module. Scans agent output for known secret patterns beyond the 17 in redact.py.

```
gateway/credential_guard.py (~150 lines)
├── LeakDetector
│   ├── load_known_secrets() — reads .env values, strips quotes
│   ├── scan(text: str) → list[LeakMatch]
│   │   ├── Check raw value presence
│   │   ├── Check base64-encoded presence
│   │   ├── Check URL-encoded presence
│   │   └── Uses Aho-Corasick (via ahocorasick pip package) for fast multi-pattern
│   ├── Actions: BLOCK (halt response, replace with warning) or REDACT (mask)
│   └── Exclude known-safe contexts (e.g., "your token has been revoked")
```

**Wire into:** `run.py` — after response, before sending. If BLOCK match → replace response with "⚠️ Response contained sensitive data and was blocked."

**Why not credential injection?** Our architecture (Claude as subprocess with shell access) makes true injection impossible. Claude can always `cat .env`. The pragmatic defense is: detect and redact on output. True injection requires WASM-level isolation or a proxy layer — that's Phase 7 (future).

#### 3e. Wire loop_detector.py (4-mode) — replace inline version

The sophisticated 4-mode detector is dead code. The inline `agent.py` version is simplistic.

**Challenge:** The 4-mode version needs result hashes, which requires parsing tool results from stream-json.

**Approach:**
- Parse `tool_result` events from stream-json in `invoke_claude_streaming()`
- Feed tool name + args hash + result hash to `LoopDetectorState`
- Replace the inline LoopDetector calls with the module calls
- The 4 modes give us: generic repeat detection, poll-no-progress, ping-pong, global circuit breaker

**Changes:**
- `gateway/agent.py` — replace inline LoopDetector with `from .loop_detector import LoopDetectorState`
- Parse tool results from stream-json output

### Tests (~25)
- Content sanitizer wiring: verify all input paths are wrapped
- Output redaction: verify agent responses are redacted
- Leak detection: raw, base64, URL-encoded secret detection
- Loop detector 4-mode: generic repeat, ping-pong, poll, circuit breaker

### Target score: Security 5 → 8

---

## Phase 4: Availability Upgrades (Session 4)

**ROI: Medium — better orchestration, parallel processing**

### What
Fix WhatsApp serialization, wire BackgroundTaskManager, add event triggers, add heartbeat.

### Why it fits
A personal agent that blocks all WhatsApp messages while answering one group is broken UX. Background tasks and heartbeat make the agent proactive rather than reactive.

### Sub-tasks

#### 4a. Fix WhatsApp serial processing

**Problem:** `whatsapp.py` processes all messages sequentially. One slow response blocks everything.

**Fix:** Use `asyncio.create_task()` instead of `await` for message handling. Each incoming message spawns a task. The per-session lock in `run.py` still ensures one-at-a-time per chat, but different chats process in parallel.

**Changes:**
- `gateway/platforms/whatsapp.py` — change `await self.on_message(...)` to `asyncio.create_task(self.on_message(...))`
- Add error handling wrapper to catch unhandled exceptions in spawned tasks
- Add concurrency limit (max 5 concurrent WhatsApp messages) via asyncio.Semaphore

#### 4b. Wire BackgroundTaskManager

**Problem:** Built but never called. The manager supports long-running tasks with "working on it" immediate response + result delivery later.

**Use cases for a personal agent:**
- `/learn` deep dives (can take 2-5 minutes) — return "Learning about X..." immediately, deliver report when done
- `/evolve` pipeline — currently blocks the session for the entire 5-stage pipeline
- Large file analysis in served groups

**Changes:**
- `gateway/commands/pipelines.py` — submit /learn and /evolve as background tasks
- `gateway/run.py` — for served group messages that trigger long processing, submit as background task
- Callback: send result to originating platform when done

#### 4c. Add event-driven triggers to routines

**Problem:** Only cron-based scheduling. No reactive triggers.

**Events worth triggering on for a personal agent:**
- `cost:threshold_80` → alert user before hitting cap
- `session:error_streak` → 3+ errors in a row → run self-diagnostic
- `whatsapp:reconnect` → bridge reconnected → send status update
- `evolve:skill_installed` → new skill ready → notify user

**Build:**
```
gateway/event_bus.py (~100 lines)
├── EventBus (singleton)
│   ├── emit(event_type: str, data: dict)
│   ├── on(event_type: str, handler: Callable)
│   └── Built on top of existing diagnostics.py event system
│
gateway/event_triggers.py (~150 lines)
├── Register default triggers:
│   ├── cost_threshold → Telegram alert
│   ├── error_streak → run self_audit
│   └── bridge_reconnect → status message
```

**Wire into:** `run.py` — emit events at key points (cost recorded, error caught, adapter connected)

#### 4d. Add heartbeat system

**From IronClaw:** Periodic LLM check of a user-authored checklist.

**Adapted for personal agent:**
```
gateway/heartbeat.py (~120 lines)
├── HeartbeatRunner
│   ├── Reads ~/.agenticEvolve/HEARTBEAT.md (user-authored)
│   ├── Every 30 min (configurable), during waking hours only
│   ├── Sends checklist to Claude: "Check each item. Reply HEARTBEAT_OK if fine."
│   ├── If not OK → send Telegram notification with findings
│   ├── Also checks: DB size, error rate, adapter connectivity
│   └── Auto-disable after 3 consecutive failures
```

**HEARTBEAT.md example:**
```markdown
# Heartbeat Checklist
- [ ] All platform adapters connected
- [ ] No sessions stuck for >10 minutes
- [ ] Daily cost under 80% of cap
- [ ] MEMORY.md under char limit
- [ ] No error spikes in last hour
```

### Config
```yaml
heartbeat:
  enabled: true
  interval_minutes: 30
  quiet_hours: [0, 7]  # midnight to 7am HKT
  notify_chat_id: "934847281"
```

#### 4e. Wire unfired hooks

5 hooks are never fired: `before_tool_call`, `after_tool_call`, `before_pipeline_stage`, `after_pipeline_stage`, `message_sending`.

**Wire:**
- `message_sending` — fire in `run.py` before sending response to platform
- `before_pipeline_stage` / `after_pipeline_stage` — fire in `evolve.py` at each stage
- `before_tool_call` / `after_tool_call` — requires stream-json parsing, defer to when we parse tool calls for loop detector (Phase 3e)

### Tests (~20)
- WhatsApp parallel: verify concurrent message handling
- Background task: submit, callback delivery, error handling
- Event triggers: emit → handler fires
- Heartbeat: HEARTBEAT_OK pass-through, alert on failure

### Target score: Availability 7 → 9

---

## Phase 5: Memory Upgrades (Session 5)

**ROI: Medium — better recall, smarter context**

### What
Add vector embeddings, enforce memory limits, improve context compaction, add memory search to dashboard.

### Why it fits
A personal agent's value compounds with memory. Better recall = more personalized responses. The agent should remember what you taught it 3 months ago, not just yesterday.

### Sub-tasks

#### 5a. Add vector embeddings (replace TF-IDF)

**Current:** `gateway/semantic.py` uses TF-IDF + cosine similarity. Lexical only — "solidity smart contract" won't match "EVM bytecode deployment".

**Upgrade to:** Local embeddings via `sentence-transformers` (runs on Apple Silicon, no API calls, free).

```
gateway/embeddings.py (~200 lines)
├── EmbeddingIndex
│   ├── model: sentence-transformers/all-MiniLM-L6-v2 (80MB, fast on M-series)
│   ├── encode(texts: list[str]) → ndarray
│   ├── build_index(sessions, learnings, instincts, memory_entries)
│   │   └── Store in ~/.agenticEvolve/cache/embeddings.npz
│   ├── search(query: str, top_k: int) → list[Match]
│   │   └── Cosine similarity, returns (text, score, source)
│   └── incremental_update(new_texts) — add without full rebuild
│
Replace semantic.py's TF-IDF with:
├── Hybrid search: FTS5 (exact keyword) + embedding (semantic) + RRF fusion
├── RRF formula: score = Σ 1/(k + rank_i) where k=60
└── Returns top-K from fused ranking
```

**Wire into:** `session_db.py:unified_search()` — replace TF-IDF layer with embedding search, fuse with FTS5 via RRF.

**Rebuild trigger:** On session end (same as current TF-IDF rebuild), plus daily cron.

#### 5b. Enforce MEMORY.md char limit

**Problem:** MEMORY.md is ~5000 chars, well past the 2200 limit. Auto-promote keeps adding without pruning.

**Fix:**
- `gateway/session_db.py:auto_promote_instincts()` — before appending, check char count
- If over limit: run a Sonnet call to consolidate (merge similar entries, remove outdated ones)
- Add `consolidate_memory()` function that:
  1. Reads MEMORY.md
  2. Sends to Sonnet: "Consolidate these notes to under 2000 chars. Merge duplicates. Remove outdated entries. Keep the most valuable insights."
  3. Writes back the consolidated version
- Run as a weekly cron job (or triggered when memory exceeds 90% of limit)

#### 5c. Improve context compaction with LLM summarization

**Current:** Truncation-based — just keeps first + last 5 messages with 100-char excerpts.

**Upgrade:** Use Sonnet (cheap) to summarize the middle section:
```python
# In context.py:compact()
middle_messages = messages[1:-5]
summary = invoke_claude_sonnet(
    f"Summarize this conversation in 3-5 bullet points:\n{middle_messages}",
    max_tokens=300
)
compacted = [messages[0], {"role": "system", "content": f"[Summary of {len(middle_messages)} earlier messages]\n{summary}"}] + messages[-5:]
```

**Cost:** ~$0.01 per compaction. Happens rarely (only when context > 60% of window).

#### 5d. Add memory search to dashboard

New dashboard page: `/memory`

```
dashboard/src/app/memory/page.tsx
├── Search box — queries /api/memory/search?q=...
├── Results grouped by source: MEMORY.md, Sessions, Learnings, Instincts
├── Memory editor — view/edit MEMORY.md content
├── Stats: total entries per source, char usage, last rebuild time
├── Embedding status: model loaded, index size, last updated
```

**New API endpoint:** `GET /api/memory/search?q=query&limit=20`
- Calls `unified_search()` from session_db
- Returns results with source labels and relevance scores

### Config
```yaml
memory:
  embedding_model: all-MiniLM-L6-v2
  memory_char_limit: 2200
  consolidation_threshold: 0.9  # consolidate at 90% of limit
  auto_consolidate: true
```

### Tests (~20)
- Embedding: encode/search returns relevant results
- RRF fusion: combined ranking is better than either alone
- Memory consolidation: stays under limit, preserves important entries
- Context compaction: LLM summary is accurate and concise

### Target score: Memory 6 → 8

---

## Phase 6: Self-Expanding Enhancement (Session 6)

**ROI: Maintain our lead — evolve pipeline is already strong**

### What
Small upgrades to the evolve pipeline + wire SubagentOrchestrator + dynamic tool building.

### Sub-tasks

#### 6a. Wire SubagentOrchestrator into evolve pipeline

**Problem:** `gateway/subagent.py` supports parallel/pipeline/DAG execution but is dead code. Evolve still uses its own ThreadPoolExecutor.

**Fix:** Refactor `evolve.py` BUILD stage to use `SubagentOrchestrator.run_parallel()`. This gives us:
- Hooks integration (subagent_spawned, subagent_ended)
- Consistent error handling and timeout
- Future: DAG execution for complex multi-skill builds

#### 6b. Skill quality metrics

Track skill usage and effectiveness:
- New table: `skill_metrics(skill_name, invoked_count, last_used, user_rating, auto_rating)`
- After each session that used a skill, score its contribution
- Surface in dashboard: which skills are most/least useful
- Auto-archive skills unused for 30 days

#### 6c. Wire BackgroundTaskManager for /learn

`/learn` deep dives can take 2-5 minutes. Currently blocks the session.

**Fix:** Submit to BackgroundTaskManager, return "Learning about X..." immediately, deliver report via Telegram when done.

### Target score: Self-Expanding 8 → 9

---

## Phase 7: Future (Not for tomorrow)

These require architectural changes beyond what we can do in a session:

1. **WASM sandbox** — Replace Docker with Wasmtime for lightweight tool isolation. Requires building WASM tool wrappers.
2. **Credential injection proxy** — HTTP proxy that intercepts all outbound requests from Claude subprocess, injects credentials, scans for leaks. Requires mitmproxy or custom proxy.
3. **Multi-agent parallel sessions** — Multiple Claude instances working on sub-tasks concurrently within one session. Requires session model redesign.
4. **pgvector migration** — Move from SQLite to PostgreSQL for production-grade vector search. Only if embedding quality from Phase 5 proves valuable.

---

## Execution Schedule

| Session | Phase | Focus | Estimated Cost | Score Impact |
|---------|-------|-------|----------------|--------------|
| **Tomorrow AM** | 1 | Smart Model Routing | ~$2 testing | Saves $10-20/day ongoing |
| **Tomorrow PM** | 2 | Provider Chain | ~$1 testing | Reliability++ |
| **Day 2 AM** | 3 | Security Hardening | ~$1 testing | Security 5→8 |
| **Day 2 PM** | 4a-4b | WhatsApp parallel + BackgroundTaskManager | ~$1 testing | Availability++ |
| **Day 3 AM** | 4c-4e | Event triggers + Heartbeat + Hooks | ~$2 testing | Availability 7→9 |
| **Day 3 PM** | 5a-5b | Vector embeddings + Memory enforcement | ~$1 testing | Memory 6→8 |
| **Day 4 AM** | 5c-5d | Context compaction + Memory dashboard | ~$1 testing | Memory++ |
| **Day 4 PM** | 6 | Self-Expanding enhancements | ~$1 testing | Self-Expanding 8→9 |

**Total estimated cost:** ~$10 in testing
**Total estimated savings:** $10-20/day from smart routing alone → pays for itself in <1 day

---

## Files Summary

### New files to create:
| File | Phase | Lines (est) |
|------|-------|-------------|
| `gateway/smart_router.py` | 1 | 300 |
| `gateway/provider_chain.py` | 2 | 350 |
| `gateway/credential_guard.py` | 3 | 150 |
| `gateway/event_bus.py` | 4 | 100 |
| `gateway/event_triggers.py` | 4 | 150 |
| `gateway/heartbeat.py` | 4 | 120 |
| `gateway/embeddings.py` | 5 | 200 |
| `HEARTBEAT.md` | 4 | 15 |
| `dashboard/src/app/memory/page.tsx` | 5 | 200 |
| Tests for all phases | 1-6 | ~150 |

### Existing files to modify:
| File | Phases | Changes |
|------|--------|---------|
| `gateway/run.py` | 1,2,3,4 | Smart routing wire, chain wire, output redaction, event emits, hooks |
| `gateway/agent.py` | 2,3 | Provider chain integration, loop detector upgrade, tool call parsing |
| `gateway/platforms/whatsapp.py` | 4 | Async message handling |
| `gateway/platforms/telegram.py` | 3 | Content sanitizer wiring |
| `gateway/session_db.py` | 5 | unified_search RRF, memory consolidation, skill_metrics table |
| `gateway/context.py` | 5 | LLM summarization for compaction |
| `gateway/evolve.py` | 6 | SubagentOrchestrator wiring |
| `gateway/commands/pipelines.py` | 4,6 | Background task submission |
| `gateway/sandbox.py` | 3 | Allowlist rules in prompt |
| `gateway/dashboard_api.py` | 1,5 | Routing stats, memory search endpoint |
| `dashboard/src/app/page.tsx` | 1 | Routing breakdown card |
| `dashboard/src/components/sidebar.tsx` | 5 | Memory page nav |
| `cron/jobs.json` | 5 | Memory consolidation cron |
| `config.yaml` | 1-5 | New config sections |

---

## Target Scorecard After All Phases

| Category | Before | After | Change |
|----------|--------|-------|--------|
| Security | 5/10 | 8/10 | +3 (output redaction, leak detection, sanitizer everywhere, loop detector) |
| Availability | 7/10 | 9/10 | +2 (parallel WhatsApp, background tasks, event triggers, heartbeat) |
| Self-Expanding | 8/10 | 9/10 | +1 (subagent orchestrator, skill metrics) |
| Memory | 6/10 | 8/10 | +2 (vector embeddings, RRF search, memory enforcement, LLM compaction) |

**Note:** Security caps at 8, not 9, because true credential injection (IronClaw's 9/10 feature) requires WASM-level isolation or a proxy layer — that's Phase 7 (future).
