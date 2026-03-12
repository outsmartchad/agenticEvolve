# agenticEvolve — Pattern Analysis

> **Scope:** 50 content files across the agenticEvolve project
> **Date range:** March 11–12, 2026 (48-hour creation burst)
> **Focus:** Memory & prompt systems, architectural coherence, gaps, contradictions, evolution of thinking
> **Analyzed by:** Claude, March 12, 2026

---

## Pattern 1: A Dramatic Architectural Pivot in 24 Hours

**The single biggest pattern in this codebase is that v1 and v2 represent fundamentally different philosophies — and the pivot happened overnight.**

v1 (March 11) was a batch cron system: bash scripts collect signals, stateless Claude calls analyze them, skills get built one per cycle. The entire orchestrator was designed to be ~150 lines of bash. The mantra was "keep the harness dumb."

v2 (March 12) is a persistent conversational agent: a Python asyncio gateway connects to Telegram/Discord/WhatsApp, sessions have continuity, memory is bounded and injected per-call, and the cron scheduler lives inside the gateway process. The mantra shifted to "build infrastructure around Claude Code."

### Evidence

- `BUILD-PLAN.md` (March 11, 6pm): "~150 lines of bash — the intelligence is in the prompts, not the orchestrator."
- `BUILD-PLAN-V2.md` (March 12, 10:42am): "v1 was a batch cron job... It had no interactivity, no memory that grows with use."
- `SOUL.md` and `README.md` are both written in the v2 voice, suggesting the pivot was decisive — not tentative.

### What this means

The pivot was motivated by a clear insight: signal scanning is just one capability, not the whole product. The v2 framing ("personal agent that grows with you") is broader and more ambitious. But the speed of the pivot means v1 artifacts are still embedded throughout the repo, creating confusion about which system is canonical.

---

## Pattern 2: Two Competing Memory Architectures Coexist

**This is the most significant contradiction in the project, especially given your focus on memory & prompts.**

### v1 Memory (Ralph-inspired, two-tier learning)

| File | Purpose | Rule |
|------|---------|------|
| `memory/state.md` | Curated knowledge | Read FIRST every cycle; deduplicated by GC |
| `memory/log.md` | Raw append-only record | Never edit, never truncate (GC archives) |
| `memory/action-items.md` | Task queue | Grep for `- [ ]`, pick top priority |
| `memory/watchlist.md` | What to track | Accounts, keywords, HN filters |

This system is fully populated and has real content (the mcp2cli skill build/reject cycle is logged). All five v1 prompts (`analyze.md`, `build-skill.md`, `gc.md`, `initialize.md`, `review-skill.md`) read from and write to these files.

### v2 Memory (hermes-agent-inspired, bounded snapshot)

| File | Purpose | Rule |
|------|---------|------|
| `memory/MEMORY.md` | Agent's notes | 2,200 char limit, frozen at session start |
| `memory/USER.md` | User profile | 1,375 char limit, frozen at session start |
| `memory/sessions.db` | Conversation history | SQLite + FTS5, searchable |

This system is designed in BUILD-PLAN-V2, implemented in the memory skill and session_db.py, and referenced by agent.py. **But MEMORY.md and USER.md don't actually exist yet.**

### Where they collide

- `agent.py` (the v2 gateway) reads `MEMORY.md` and `USER.md` — files that don't exist.
- The `evolve` skill (v2) references `memory/action-items.md`, `memory/log.md`, and `config.sh` — all v1 files.
- The `memory` skill (v2) manages `MEMORY.md`/`USER.md` with bounded char limits, but the v1 prompts manage `state.md` with a 50-line limit.
- The v1 prompts still exist in `prompts/` and are syntactically ready to run. Nothing marks them as deprecated.

### The gap

There's no migration path defined. If you run the v2 gateway, it will reference empty memory files. If you run `ae cycle` (v1), it will populate v1 memory files that the gateway ignores. The two systems operate on parallel tracks with no bridge.

---

## Pattern 3: The Prompt Pipeline Got Partially Orphaned

**v1 had a carefully designed 5-prompt pipeline. v2 collapsed it into a single "evolve" skill — but the collapse is incomplete.**

### v1 Prompt System (5 specialized agents)

```
initialize.md → One-time setup, scaffolds environment
analyze.md    → Reads signals, scores them, picks ONE action item
build-skill.md → Builds a skill from the top action item
review-skill.md → Read-only validation (security, quality, redundancy)
gc.md         → Weekly maintenance (prune, deduplicate, validate)
```

Each prompt had strict rules: the analyzer picks exactly one item, the builder builds exactly one skill, the reviewer is read-only. The system enforced discipline through prompt design.

### v2 Replacement (single evolve skill)

The `evolve` skill combines collect + analyze + build into one invocation. It uses a scoring system (relevance + novelty + actionability, 0–9) with a build threshold of 7+.

### What got lost

- **The human review gate.** v1 had three gates (auto-reviewer, queue, human review). v2's evolve skill auto-installs skills directly to `~/.claude/skills/` with only a "don't overwrite existing" guard. This is a significant safety regression — BUILD-PLAN-V1 explicitly warned that "bad skills compound over time."
- **The GC agent.** No v2 equivalent exists. The garbage collection prompt (`gc.md`) handles entropy management — pruning stale items, deduplicating state, detecting unused skills, validating collectors. Nothing in v2 replaces this.
- **The struggle-as-signal loop.** v1's BUILD_FAILED pattern (log failures → next analyzer reads them → curates lessons into state.md) has no v2 equivalent. The gateway doesn't persist or learn from failures.
- **The reviewer agent.** The read-only validation step (no hardcoded keys, valid frontmatter, no redundancy) is gone. The evolve skill just validates line count.

### What improved

- The evolve skill is more flexible — it can use WebFetch and MCP tools to research, not just read local JSON files.
- Scoring is more explicit (0–9 composite score vs. implicit "pick the most actionable").
- The skill can be triggered on-demand from any platform, not just via cron.

---

## Pattern 4: Significant Gaps Between Plan and Implementation

### Files that are designed but don't exist

| Planned in BUILD-PLAN-V2 | Actual status |
|---------------------------|---------------|
| `memory/MEMORY.md` | Does not exist |
| `memory/USER.md` | Does not exist |
| `gateway/session.py` | Functionality absorbed into `run.py` and `session_db.py` |
| `cron/scheduler.py` | Functionality absorbed into `run.py._cron_loop()` |
| `cron/output/` directory | Does not exist (created at runtime) |
| `ae setup` wizard | Not implemented |
| `ae doctor` diagnostics | Not implemented |
| `ae gateway install` | Not implemented |
| `signal-history.db` (dedup) | Never created |

### Implementation shortcuts in the gateway

- **Cron expression parsing is stubbed.** `_run_due_jobs()` handles `interval` and `once` schedule types properly, but for `cron` type it just adds 24 hours — so `0 9 * * 1-5` (weekdays at 9am) would run every 24h regardless.
- **Cost tracking format mismatch.** `agent.py:get_today_cost()` parses tab-separated fields where column 4 has `$` prefix. `run.py._log_cost()` writes tab-separated with `$` prefix in column 4. The formats align, but the v1 `BUILD-PLAN.md` specified space-separated with no `$` prefix. If you ever mix v1 and v2 cost logs, parsing will break.
- **WhatsApp bridge is written but untested.** The `bridge.js` and `whatsapp.py` adapter exist, but the README honestly marks it "Written, untested."

### The `ae` CLI is stuck on v1

The actual `ae` file in the repo is still the v1 CLI from BUILD-PLAN.md. The v2 commands (`ae gateway`, `ae memory`, `ae sessions list`, `ae config`, `ae setup`, `ae doctor`) are designed in BUILD-PLAN-V2 but not implemented. Running `ae gateway` today would fall through to the help text.

---

## Pattern 5: Key Contradictions Across Documents

### 1. Session continuity

- **v1 BUILD-PLAN** (Patterns Borrowed table): "Fresh context each iteration... No session continuity. Each `claude -p` starts clean."
- **v1 BUILD-PLAN** (What we deliberately cut table): "Session continuity (`--resume`) — Fresh context is a feature. Prevents accumulated confusion."
- **v2 BUILD-PLAN**: "Session continuity — conversation history is fed back into each `claude -p` call within a session (last 20 turns, 8K chars max)."

The v1 plan explicitly cut session continuity as an anti-pattern. v2 re-introduced it as a core feature. Both positions are well-reasoned — the tension is real and worth noting: for autonomous batch processing, statelessness prevents accumulated confusion; for conversational agents, statelessness makes the agent amnesiac.

### 2. Skill safety gates

- **v1**: Three gates (auto-reviewer → queue → human review). "Skills modify Claude's behavior — bad skills compound over time."
- **v2 evolve skill**: Auto-installs to `~/.claude/skills/` with only a line-count check and "don't overwrite existing" guard. No reviewer, no human gate.
- **SOUL.md**: "After completing a complex task (5+ tool calls), evaluate if the workflow should be saved as a reusable skill... create it in ~/.claude/skills/ using the Write tool." — This is even more permissive, no validation at all.

### 3. Technology stance

- **v1**: "No frameworks, no Node.js in the core loop — bash + curl + jq + claude CLI."
- **v2**: Python asyncio gateway, Node.js WhatsApp bridge, SQLite, pip dependencies.

This isn't a contradiction so much as an acknowledged evolution. v2's BUILD-PLAN explains the reasoning clearly. But the v1 collector scripts (pure bash) still exist alongside the v2 Python gateway, creating a mixed-language codebase.

### 4. Memory file references

- **SOUL.md**: "check for AGENTS.md in the working directory" — no AGENTS.md exists anywhere.
- **Architecture diagrams** (both README.md and BUILD-PLAN-V2): Show "SOUL.md + AGENTS.md" as the personality layer. AGENTS.md is referenced but never defined.
- **evolve skill**: References `config.sh` (v1), but `config.yaml` (v2) is the canonical config.

---

## Summary: Where the Project Stands

agenticEvolve is a thoughtful project with strong design instincts — the decision to build *on top of* Claude Code rather than reimplementing an agent loop is smart, and the hermes-agent-inspired memory system is well-designed. The v1 → v2 pivot shows genuine learning: you identified that a batch signal scanner isn't enough and that the real value is a persistent personal agent.

The main risk right now is **v1/v2 drift**. Two architectures, two memory systems, two prompt pipelines, and two CLI designs coexist without clear boundaries. Specifically:

1. **Create MEMORY.md and USER.md** — the v2 memory system is designed and the skill is ready, but the actual files don't exist. The gateway will read empty strings.
2. **Deprecate or migrate v1 prompts** — the five prompts in `prompts/` are well-crafted but orphaned. Either port their wisdom into v2 skills (especially the reviewer and GC logic) or mark them as v1-only.
3. **Restore the safety gate** — the evolve skill auto-installs skills without review. The v1 three-gate approach was there for a reason. Even a simple "queue + manual approve" step would catch issues.
4. **Update the `ae` CLI** — it's still v1. The v2 commands are designed but not wired up.
5. **Fix cron expression parsing** — the "just add 24h" shortcut means only daily intervals work correctly.
