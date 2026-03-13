---
name: unf
description: Install and use unf — a local-first background daemon that auto-snapshots every text file on save, storing versions in SQLite + content-addressed object store. Use when the user wants file version safety before long Claude sessions, needs to undo file changes that weren't committed, wants automatic local backups, says "I lost my changes", "can we revert that file", or needs a safety net before running agents in bypass mode.
argument-hint: [install | watch <dir> | log <file> | restore <file> <version>]
disable-model-invocation: true
allowed-tools: Bash(unf *), Bash(brew *)
---

# unf — Automatic File Versioning Daemon

`unf` watches directories and snapshots every text file on save. Versions stored in SQLite metadata + content-addressed object store. It fills the gap between "I just saved" and "I committed to git" — protecting against agent accidents before you're ready to commit.

## Install

```bash
brew install unf
# or
curl -fsSL https://unf.sh/install | sh
```

Note: Check that the package is available for your platform. If `brew install unf` fails, try the curl installer or check https://github.com/ruleb/unf for the latest install instructions.

## Start Watching a Directory

```bash
unf watch ~/Desktop/projects/my-app
unf watch .   # watch current directory
```

The daemon runs in the background and snapshots on every file save.

## View File History

```bash
unf log src/index.ts              # list all versions with timestamps
unf log src/index.ts --since 1h   # last hour only
```

## Restore a Version

```bash
unf restore src/index.ts 3    # restore to version 3
unf restore src/index.ts --time "10 minutes ago"
```

## UI

```bash
unf ui   # open local web UI to browse history visually
```

## Key Properties

- Skips binaries and respects `.gitignore`
- Content-addressed storage — no duplicate data
- Works alongside git — fills the gap for uncommitted in-progress work
- No cloud dependency — all local
- Minimal CPU/disk overhead — designed to run continuously

## When to Use

Add `unf watch .` before starting a long Claude Code session, especially in `bypassPermissions` mode. If the agent overwrites files you weren't ready to lose, `unf restore` gets them back instantly.

Also valuable during `absorb` or `evolve` operations where multiple files may be modified in a single run.

Source: https://github.com/ruleb/unf
