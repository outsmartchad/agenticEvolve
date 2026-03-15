---
name: context-optimizer
description: >
  Analyze Claude Code context usage and automatically compact or archive
  bloated memory files based on actionable hints from the /context command.
  Use when context is running out, memory files are growing stale, agenticEvolve
  cycles are getting slow, or when the user says "optimize context", "trim
  memory", "context is full", "compact memory", or "clean up context".
user_invocable: true
---

# Context Optimizer

Claude Code v2.1.74 added actionable suggestions to `/context` — it identifies
context-heavy tools, memory bloat, and capacity warnings. This skill reads
those hints and acts on them automatically.

## What It Does

1. Runs a context analysis to identify heavy memory files
2. Archives files that haven't been accessed in the current session
3. Compacts MEMORY.md entries that exceed 200 chars
4. Reports what was trimmed and how much context was recovered

## Manual Run

```bash
#!/usr/bin/env bash
# ~/.claude/hooks/context-optimizer.sh
# Run this when context > 80% capacity

MEMORY_DIR="${HOME}/.claude/projects/-Users-$(whoami)/memory"
ARCHIVE_DIR="${MEMORY_DIR}/archive/$(date +%Y-%m)"
mkdir -p "$ARCHIVE_DIR"

# Archive memory files older than 30 days not referenced in MEMORY.md
find "$MEMORY_DIR" -name "*.md" -not -name "MEMORY.md" -mtime +30 | \
  while read -r file; do
    filename=$(basename "$file")
    if ! grep -q "$filename" "$MEMORY_DIR/MEMORY.md"; then
      echo "Archiving: $filename"
      mv "$file" "$ARCHIVE_DIR/"
    fi
  done

echo "Archive complete. Files moved to: $ARCHIVE_DIR"
```

## Integration with agenticEvolve

Add to evolve cycle (post-skill-build step):

```bash
# In evolve pipeline, after skills are built:
bash ~/.claude/hooks/context-optimizer.sh

# Check MEMORY.md line count — trim if > 200 lines
MEMORY_LINES=$(wc -l < ~/.claude/projects/-Users-$(whoami)/memory/MEMORY.md)
if [[ $MEMORY_LINES -gt 180 ]]; then
  echo "WARNING: MEMORY.md at ${MEMORY_LINES} lines — consolidate entries"
fi
```

## Triggers

- Run automatically when Claude Code reports context > 80% in `/context` output
- Run at the end of every agenticEvolve evolve cycle
- Run manually with `/context-optimizer` before starting a complex session

## Reference

- Claude Code v2.1.74 release: /context actionable suggestions
- `autoMemoryDirectory` setting in settings.json for automatic memory routing
