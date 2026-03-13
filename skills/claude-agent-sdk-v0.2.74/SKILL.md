---
name: claude-agent-sdk-session
description: >
  Audit deployed Claude Code skills for user-invocable metadata correctness and rename stale
  session files using the Claude Agent SDK renameSession API. Use when the user says "audit
  skills", "check skill metadata", "fix user-invocable flags", "rename session", "clean up
  sessions", "skill leakage", or wants to ensure skills are correctly gated behind
  user-invocable settings after upgrading to Claude Agent SDK v0.2.74+.
argument-hint: "[audit-skills | rename-session <old-name> <new-name>]"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - Edit
---

# Claude Agent SDK — Skill Audit & Session Rename

Claude Agent SDK v0.2.74 fixes two things:
1. **user-invocable:false skill leakage** — skills marked non-user-invocable were incorrectly
   appearing in `supportedCommands`, exposing internal skills to users.
2. **renameSession API** — renames session files without losing conversation history.

---

## Mode 1: Audit Skills for user-invocable Correctness

Scan all skill files and flag any that are missing the `user-invocable` field or have it set
incorrectly relative to their intended visibility.

```bash
# Find all SKILL.md files
find ~/.claude/skills -name "SKILL.md" | sort

# Check which skills are missing user-invocable field
grep -rL "user-invocable" ~/.claude/skills/

# Check which skills have user-invocable: false (should be hidden from /commands)
grep -rl "user-invocable: false" ~/.claude/skills/
```

**Fix pattern** — add to frontmatter of internal/pipeline skills:
```yaml
user-invocable: false
```

Omit the field (or set `true`) for skills meant to appear in `/commands` and be callable by the user.

**Why this matters:** Before v0.2.74, `user-invocable: false` skills leaked into
`supportedCommands`. If you have pipeline skills (e.g., BUILDER, SCORER) that should only
be invoked by agents, they were visible to users. After upgrading, audit to confirm intent.

---

## Mode 2: Rename a Session

Use the `renameSession` API when a session file has a stale or auto-generated name.

```typescript
import { ClaudeAgentSDK } from "@anthropic-ai/claude-agent-sdk";

const sdk = new ClaudeAgentSDK();

// Rename a session by its current name
await sdk.renameSession({
  sessionId: "<session-id-or-current-name>",
  newName: "<descriptive-new-name>",
});
```

Or via CLI if the SDK exposes a command:
```bash
npx claude-agent-sdk rename-session "<old-name>" "<new-name>"
```

**Why this matters:** agenticEvolve creates sessions per cycle. Without renaming, session
files accumulate with auto-generated IDs. `renameSession` lets you tag sessions with
cycle dates or task names (e.g., `evolve-2026-03-13-build`) for easier retrieval.

---

## Audit Checklist

- [ ] All pipeline skills (BUILDER, SCORER, LEARN) have `user-invocable: false`
- [ ] All user-facing skills omit `user-invocable` or set it to `true`
- [ ] No internal skill names appear in the `/` command palette
- [ ] Sessions for current cycle are renamed with date + task suffix

---

Source: https://github.com/anthropics/claude-agent-sdk-typescript/releases/tag/v0.2.74
