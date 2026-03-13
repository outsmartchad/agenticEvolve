# Pipelines

agenticEvolve ships four main pipelines and a garbage collector. All run in background with streaming progress messages to your platform.

---

## `/evolve` — Signal → Skill

5-stage pipeline: **COLLECT → ANALYZE → BUILD → REVIEW → REPORT**

1. **COLLECT** — Signal collectors scan GitHub trending, Hacker News, and X
2. **ANALYZE** — Scores signals on relevance, novelty, actionability (0-9)
3. **BUILD** — Creates skills using [skill-creator](https://github.com/anthropics/claude-plugins-official) standards for candidates scoring ≥ 7.0
4. **REVIEW** — Separate agent validates security, quality, correctness
5. **REPORT** — Skills land in `skills-queue/` — requires human `/approve` to install

**Flags:**
- `--dry-run` — stops after ANALYZE, shows what would be built
- `--skip-security-scan` — bypass the security scanner
- `--model <name>` — override the model for this run

---

## `/absorb <target>` — Deep Scan → Self-Improve

5-stage pipeline: **SCAN → GAP → PLAN → IMPLEMENT → REPORT**

1. **SCAN** — Deep-scans target (clones repos, reads source, maps architecture)
2. **GAP** — Compares target patterns against our system
3. **PLAN** — Creates concrete file-level implementation plan
4. **IMPLEMENT** — Modifies our system files to absorb improvements
5. **REPORT** — Changes logged in learnings DB with structured summary

**Flags:**
- `--dry-run` — stops after GAP, shows gaps by priority
- `--skip-security-scan` — bypass the security scanner
- `--model <name>` — override the model

---

## `/learn <target>` — Pattern Extraction

Deep-dives a repo, URL, or technology. Extracts patterns for operational benefit — not book reports. Returns structured findings with three verdicts:

| Verdict | Meaning |
|---------|---------|
| **ADOPT** | Use it directly |
| **STEAL** | Take the patterns, skip the dependency |
| **SKIP** | Not useful for our workflow |

Findings persist in SQLite+FTS5, searchable via `/learnings`. Supports `--skip-security-scan`.

---

## `/do <instruction>` — Natural Language Command

Parses free-text instructions into structured commands using a lightweight Claude Haiku call, then executes them in background with 1-minute progress reports.

```
/do absorb this repo https://github.com/foo/bar and skip the security scan
→ Parsed: /absorb https://github.com/foo/bar --skip-security-scan (confidence: 95%)
→ Running...
→ [/absorb ...] Still running... (60s elapsed, ~1 min)
→ [/absorb ...] Completed in 245s.
```

**Synonym mapping:**
- "study" / "research" → `/learn`
- "integrate" / "steal from" → `/absorb`
- "find new tools" → `/evolve`
- "preview" / "just check" → `--dry-run`
- "skip security" / "no scan" → `--skip-security-scan`

---

## `/gc` — Garbage Collection

Cleans stale sessions (30d), empty sessions (24h), orphan skills (7d), checks memory entropy (85% threshold), rotates logs. Supports `--dry` preview mode.
