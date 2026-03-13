# Skills

16 skills installed. All follow the [official skill-creator](https://github.com/anthropics/claude-plugins-official) quality standards — pushy trigger descriptions, imperative form, progressive disclosure.

## Installed Skills

### Core (7 original)

| Skill | Purpose |
|-------|---------|
| [session-search](../skills/session-search/SKILL.md) | FTS5 search across past conversations — "we talked about...", "remember when..." |
| [cron-manager](../skills/cron-manager/SKILL.md) | Schedule recurring agent tasks — "run every", "remind me", "schedule" |
| [brave-search](../skills/brave-search/SKILL.md) | Web search via Brave API — "search for", "look up", "what's the latest" |
| [skill-creator](../skills/skill-creator/SKILL.md) | Create, eval, benchmark, and optimize skills (official Anthropic plugin) |
| [nah](../skills/nah/SKILL.md) | PreToolUse permission guard (256+ stars) — classify + allow/ask/block |
| [agent-browser-protocol](../skills/agent-browser-protocol/SKILL.md) | Deterministic browser automation MCP (333+ stars, 90.5% Mind2Web) |
| [unf](../skills/unf/SKILL.md) | Auto file versioning daemon — safety net before long agent sessions |

### Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) (73k+ stars)

Refined for individual dev/creator workflows with agenticEvolve integration notes and builder-style voice.

| Skill | Purpose |
|-------|---------|
| [article-writing](../skills/article-writing/SKILL.md) | Write articles, blogs, newsletters in a distinctive voice — not AI slop |
| [video-editing](../skills/video-editing/SKILL.md) | AI-assisted video editing pipeline (FFmpeg, Remotion, ElevenLabs) |
| [autonomous-loops](../skills/autonomous-loops/SKILL.md) | Patterns for autonomous Claude Code loops and multi-agent pipelines |
| [continuous-learning-v2](../skills/continuous-learning-v2/SKILL.md) | Instinct-based learning from sessions via hooks with confidence scoring |
| [deep-research](../skills/deep-research/SKILL.md) | Multi-source cited research reports with quality gates |
| [eval-harness](../skills/eval-harness/SKILL.md) | Eval-driven development with pass@k metrics and regression suites |
| [market-research](../skills/market-research/SKILL.md) | Market sizing, competitive analysis, technology evaluation |
| [security-review](../skills/security-review/SKILL.md) | Security best practices checklist for code (auth, input, XSS, CSRF, etc.) |
| [security-scan](../skills/security-scan/SKILL.md) | Scan Claude Code config for misconfigurations using AgentShield |

## Skill Triggering

Skills with `disable-model-invocation: true` (nah, ABP, unf, cron-manager) only trigger when explicitly invoked — they're install/config tools, not general-purpose.

All other skills use "pushy" descriptions per skill-creator guidelines to reduce undertriggering. Claude reads the skill metadata and decides when to consult the full SKILL.md body.

## Adding New Skills

Skills are added through three paths:

1. **`/evolve`** — automated pipeline creates skills from trending signals, lands in `skills-queue/`
2. **`/absorb`** — deep-scanning repos can produce skills as improvements
3. **Manual** — create a `SKILL.md` with proper frontmatter in `~/.claude/skills/<name>/`

All automated skills require human `/approve` before installation.
