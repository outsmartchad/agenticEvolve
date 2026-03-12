---
name: unf
description: Install and use unf — a local-first background daemon that auto-snapshots every text file on save, storing versions in SQLite + object store. Lets you rewind any file to any point in time. Use when the user wants file version safety before long Claude sessions, needs to undo file changes that weren't committed, or wants automatic local backups of their working directory.
argument-hint: [install | watch <dir> | log <file> | restore <file> <version>]
disable-model-invocation: true
allowed-tools: Bash(unf *), Bash(brew *)
---

# unf — Automatic File Versioning Daemon

`unf` watches directories you specify and snapshots every text file on save. Versions stored in SQLite metadata + content-addressed object store. Protects against agent accidents before you commit to git.

## Install

```bash
brew install unf
# or
curl -fsSL https://unf.sh/install | sh
```

## Start Watching a Directory

```bash
unf watch ~/Desktop/projects/my-app
unf watch .   # watch current directory
```

The daemon runs in the background and snapshots on every file save.

## View File History

```bash
unf log src/index.ts          # list all versions with timestamps
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

## When to Use

Add `unf watch .` before starting a long Claude Code session in `bypassPermissions` mode. If the agent overwrites files you weren't ready to lose, `unf restore` gets them back.

Source: https://github.com/ruleb/unf
