# agenticEvolve vs IronClaw — Feature Comparison

> **agenticEvolve**: Python asyncio personal AI agent gateway (post Phase 1-6 upgrades)
> **IronClaw**: NEAR AI's production-grade Rust agent framework

---

## Scoring Key

| Score | Meaning |
|-------|---------|
| 9-10 | Production-grade, battle-tested |
| 7-8 | Solid implementation, minor gaps |
| 5-6 | Functional but missing hardening |
| 3-4 | Partial coverage |
| 1-2 | Minimal or absent |

---

## 1. Security

| Aspect | IronClaw | agenticEvolve | Gap |
|--------|----------|---------------|-----|
| **Input sanitization** | Strict type-safe parsing via Rust serde; rejects malformed payloads at deserialization | `content_sanitizer` applied at every ingest point; regex-based pattern matching | Rust's type system catches entire classes of injection that regex cannot |
| **Output redaction** | Structured output filters with allowlist fields per consumer | Output redaction layer strips secrets/PII before relay to chat platforms | Comparable intent; IronClaw's allowlist model is more restrictive by default |
| **Credential protection** | Credential injection proxy — agents never see raw secrets; secrets live in a separate process boundary | `credential_guard.py` scans messages for leaked tokens/keys; sandbox deny patterns block sensitive commands | No injection proxy — credentials exist in-process; detection is reactive, not preventive |
| **Sandbox isolation** | WASM sandbox per agent — memory/CPU/syscall boundaries enforced by runtime | Deny-pattern list blocks dangerous shell commands; no true process/memory isolation | **Biggest gap.** No WASM or container sandbox; a crafted prompt could still reach the host |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **9** | **6** |

**What's missing:** WASM/container sandbox, credential injection proxy, type-safe input parsing.

---

## 2. Provider Resilience

| Aspect | IronClaw | agenticEvolve | Gap |
|--------|----------|---------------|-----|
| **Retry** | Configurable exponential backoff with jitter; per-provider retry budgets | Retry decorator with exponential backoff | No per-provider budget tracking |
| **Circuit breaker** | Three-state (closed/half-open/open) with sliding-window failure rate | CircuitBreaker decorator, same three-state model | Comparable |
| **Caching** | Hot/cold tier response cache; hot in-memory, cold in persistent store; TTL + LRU eviction | Cache decorator (in-memory); no tiered storage | No cold-tier persistence; cache lost on restart |
| **Rate limiting** | Token-bucket per provider with backpressure signaling | Not explicitly implemented as a standalone layer | Missing dedicated rate limiter |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **9** | **7** |

**What's missing:** Tiered cache (hot/cold), per-provider retry budgets, dedicated rate limiter.

---

## 3. Smart Routing

| Aspect | IronClaw | agenticEvolve | Gap |
|--------|----------|---------------|-----|
| **Complexity scoring** | Task-type classifier (likely ML-based) mapping to model tiers | 13-dimension regex complexity scorer — code detection, math, reasoning depth, etc. | agenticEvolve's scorer is more transparent/debuggable; IronClaw's may generalize better |
| **Model selection** | Routes to optimal model from a registry; supports fallback chains | Per-message Sonnet/Opus routing based on score thresholds | Only two model tiers vs IronClaw's N-tier registry |
| **Cascade detection** | Detects task escalation patterns and re-routes mid-conversation | Not implemented | No mid-conversation re-routing |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **8** | **7** |

**What's missing:** N-tier model registry, mid-conversation cascade re-routing.

---

## 4. Memory

| Aspect | IronClaw | agenticEvolve | Gap |
|--------|----------|---------------|-----|
| **Vector search** | Embeddings with configurable backends (likely HNSW-based) | `sentence-transformers/all-MiniLM-L6-v2` embeddings, vector similarity search | Comparable; IronClaw may support larger/swappable models |
| **Fusion ranking** | RRF fusion across multiple retrieval signals | RRF fusion search combining keyword + vector results | Comparable |
| **Memory limits** | Configurable per-agent memory budgets; auto-eviction | LLM context compaction + memory consolidation | No hard per-agent memory budget; compaction is heuristic |
| **Consolidation** | Auto-archival of stale memories with summarization | Memory consolidation merges related entries; memory dashboard for inspection | Similar intent; IronClaw's archival is more automated |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **8** | **7** |

**What's missing:** Configurable per-agent memory budgets, pluggable embedding backends, automated archival policies.

---

## 5. Availability

| Aspect | IronClaw | agenticEvolve | Gap |
|--------|----------|---------------|-----|
| **Parallel handling** | Tokio async runtime; bounded concurrency per endpoint | asyncio + Semaphore(5) for parallel WhatsApp processing | Both async; Rust's Tokio has lower overhead per task |
| **Health monitoring** | Structured heartbeat with diagnostics payload; dead-agent detection | Heartbeat system reporting liveness to monitoring | No structured diagnostics payload or dead-agent recovery |
| **Event system** | Event bus with typed events; supports pub/sub + triggers | Event bus + triggers; hooks wired across all phases | Comparable in design; IronClaw has typed event schemas |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **9** | **7** |

**What's missing:** Typed event schemas, dead-agent detection/recovery, lower-overhead concurrency runtime.

---

## 6. Self-Expanding

| Aspect | IronClaw | agenticEvolve | Gap |
|--------|----------|---------------|-----|
| **Skill creation** | Skill registry with versioned definitions; agents can register new skills | SubagentOrchestrator hooks into evolve; `/learn` command for background skill acquisition | Comparable intent; IronClaw has formal versioning |
| **Quality metrics** | Per-skill success rate, latency percentiles; auto-archival below threshold | `skill_metrics` table tracking usage and outcomes | No auto-archival of underperforming skills |
| **Background tasks** | Managed task scheduler with priority queues | BackgroundTaskManager handles `/learn` and async work | No priority queue; simpler FIFO scheduling |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **8** | **7** |

**What's missing:** Skill versioning, auto-archival of low-quality skills, priority-based task scheduling.

---

## 7. Architecture

| Aspect | IronClaw | agenticEvolve |
|--------|----------|---------------|
| **Language** | Rust — memory safety, zero-cost abstractions, no GC pauses | Python 3.x — rapid iteration, rich ML/NLP ecosystem |
| **Deployment** | Container-native; designed for multi-node orchestration | Single-process; runs on one machine (personal use) |
| **Testing** | Likely property-based + integration test suites; Rust compiler catches many bugs at compile time | Ad-hoc testing; Python's dynamic typing requires more runtime checks |
| **Target audience** | Teams building production AI agent systems | Solo developer personal agent gateway |

| | IronClaw | agenticEvolve |
|--|----------|---------------|
| **Score** | **9** | **5** |

**What's missing:** Formal test suite, multi-node deployment, compile-time safety guarantees.

---

## Summary Scorecard

| Category | IronClaw | agenticEvolve | Delta |
|----------|----------|---------------|-------|
| Security | 9 | 6 | -3 |
| Provider Resilience | 9 | 7 | -2 |
| Smart Routing | 8 | 7 | -1 |
| Memory | 8 | 7 | -1 |
| Availability | 9 | 7 | -2 |
| Self-Expanding | 8 | 7 | -1 |
| Architecture | 9 | 5 | -4 |
| **Average** | **8.6** | **6.6** | **-2.0** |

---

## Key Takeaways

1. **Largest gaps are structural** — WASM sandboxing and Rust's compile-time safety are not things you bolt on to a Python project. These account for most of the security and architecture delta.

2. **Feature parity is surprisingly close** — For a personal agent gateway, agenticEvolve covers ~77% of IronClaw's feature surface across all categories. The 6-phase upgrade plan successfully adopted the most impactful patterns.

3. **Highest-ROI next steps** for agenticEvolve:
   - Add a container/subprocess sandbox for command execution (closes the biggest security gap)
   - Implement tiered caching with SQLite cold tier (cheap win for resilience)
   - Add a formal test suite (biggest architecture gap that's actually fixable)

4. **Intentional differences** — agenticEvolve optimizes for iteration speed and ML ecosystem access (Python). IronClaw optimizes for safety and throughput (Rust). These are valid tradeoffs for their respective use cases.
