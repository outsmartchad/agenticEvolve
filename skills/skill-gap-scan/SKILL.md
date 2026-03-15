---
name: skill-gap-scan
description: >
  Scan an external Claude Code skill catalog or repo against your local
  ~/.claude/ skills and identify gaps — skills that exist upstream but not
  locally. Use when auditing your skill coverage against a community repo,
  "what skills am I missing", "compare my skills to everything-claude-code",
  "find skill gaps", or before an evolve cycle to discover high-value skills
  to adopt.
user_invocable: true
---

# Skill Gap Scanner

Compares a remote skill catalog (e.g. affaan-m/everything-claude-code) against
your local `~/.claude/skills/` to surface adoptable skills ranked by value.

## Quick Scan

```bash
# List your local skills
ls ~/.claude/skills/

# Clone or pull the reference catalog
CATALOG_DIR="/tmp/ecc-catalog"
if [[ -d "$CATALOG_DIR" ]]; then
  git -C "$CATALOG_DIR" pull --quiet
else
  git clone --depth=1 https://github.com/affaan-m/everything-claude-code \
    "$CATALOG_DIR" --quiet
fi

# Find skills in catalog not in your local set
LOCAL_SKILLS=$(ls ~/.claude/skills/ | sed 's/\.md$//')
CATALOG_SKILLS=$(ls "$CATALOG_DIR/skills/" 2>/dev/null | sed 's/\.md$//')

echo "=== GAPS ==="
comm -13 <(echo "$LOCAL_SKILLS" | sort) <(echo "$CATALOG_SKILLS" | sort)
```

## Score Gaps for Adoption

For each gap skill, score it on the standard 0-9 rubric:
- **RELEVANCE** — does it match your stack (TypeScript, AI agents, developer tools)?
- **NOVELTY** — do you already have this capability some other way?
- **ACTIONABILITY** — can you drop it in and use it today?

Adopt if composite >= 7.0.

## Adoption Checklist

For each gap skill you decide to adopt:

1. Read the skill's YAML frontmatter — verify `user_invocable` and `description`
2. Check for hardcoded secrets, placeholder values, or domain-specific assumptions
3. Adapt `description` to your trigger vocabulary
4. Copy to `~/.claude/skills/<name>.md`
5. Test with `/skill-name` in a fresh session

## Reference

- everything-claude-code: https://github.com/affaan-m/everything-claude-code
- agenticEvolve skill standards: under 100 lines, valid YAML, no secrets
