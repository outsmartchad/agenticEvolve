---
name: lazygit
description: >
  Launch and use lazygit — a terminal UI for git that reduces cognitive load on
  branch, commit, stash, merge, rebase, and push workflows. Use when the user
  says "open lazygit", "git UI", "visual git", "stage hunks", "interactive rebase",
  "cherry-pick commits", "manage branches visually", or wants a faster git workflow
  without memorizing complex git commands. Also trigger when the user wants to
  squash commits, resolve merge conflicts interactively, or navigate git history visually.
argument-hint: "lazygit [optional: path to repo]"
allowed-tools:
  - Bash
  - Read
---

# lazygit

Terminal UI for git — keyboard-driven interface for staging, committing,
branching, rebasing, and pushing without memorizing git syntax.

## Installation

```bash
# macOS
brew install lazygit

# Verify
lazygit --version
```

## Launch

```bash
# In current repo
lazygit

# In a specific repo
lazygit -p /path/to/repo
```

## Key Bindings (essential)

| Panel     | Key       | Action                          |
|-----------|-----------|---------------------------------|
| Files     | `space`   | Stage/unstage file              |
| Files     | `a`       | Stage all / unstage all         |
| Files     | `c`       | Commit staged changes           |
| Files     | `A`       | Amend last commit               |
| Files     | `e`       | Open file in editor             |
| Branches  | `n`       | New branch                      |
| Branches  | `space`   | Checkout branch                 |
| Branches  | `M`       | Merge branch into current       |
| Branches  | `r`       | Rebase current onto branch      |
| Commits   | `s`       | Squash commit into previous     |
| Commits   | `r`       | Rename commit message           |
| Commits   | `e`       | Edit commit (interactive rebase)|
| Commits   | `p`       | Pick commit (cherry-pick)       |
| Stash     | `n`       | New stash                       |
| Stash     | `space`   | Apply stash                     |
| Global    | `P`       | Push                            |
| Global    | `p`       | Pull                            |
| Global    | `?`       | Show keybindings for panel      |
| Global    | `q`       | Quit                            |

## Claude Code Integration

To bind lazygit to a key in Claude Code, add to `~/.claude/settings.json`:

```json
{
  "keybindings": [
    {
      "key": "ctrl+g",
      "command": "shell",
      "args": "lazygit -p $(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    }
  ]
}
```

## Custom Keybindings in lazygit

Config lives at `~/.config/lazygit/config.yml`:

```yaml
keybinding:
  universal:
    quit: 'q'
  commits:
    squashDown: 's'
    rewordCommit: 'r'
  branches:
    createPullRequest: 'o'
```

## Workflow Examples

**Stage hunks interactively (not whole files):**
1. Press `enter` on a file in the Files panel
2. Navigate to a hunk with `↑`/`↓`
3. Press `space` to stage individual hunks

**Interactive rebase (squash last 3 commits):**
1. Go to Commits panel
2. Navigate to the 3rd commit back
3. Press `e` to start interactive rebase from there
4. Press `s` on each commit to squash

**Cherry-pick a commit to current branch:**
1. Switch to Branches panel, navigate to source branch
2. In Commits panel, press `c` to copy commit
3. Switch back to your branch
4. Press `v` to paste (cherry-pick)

Source: https://github.com/jesseduffield/lazygit
