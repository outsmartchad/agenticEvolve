# Security

agenticEvolve enforces security at every layer — from code scanning to runtime permission control.

---

## Security Scanner

All pipelines (`/absorb`, `/learn`, `/evolve`) run an automated security scan on external repos before processing.

### Threat Detection

| Threat | Examples |
|--------|----------|
| Credential exfiltration | Reading `~/.ssh`, `~/.aws`, macOS Keychain dumps |
| Reverse shells | Bash/netcat/Python reverse shells |
| Remote code execution | `curl \| bash`, download-and-execute patterns |
| Obfuscated payloads | Base64-encoded shell commands, hex payloads |
| Malicious install hooks | npm `postinstall`, Python `setup.py` cmdclass |
| Destructive commands | `rm -rf /`, fork bombs, disk wipes |
| Crypto miners | xmrig, stratum connections |
| macOS persistence | LaunchAgents, login items, TCC resets |

### Verdicts

- **BLOCKED** — critical threat detected, pipeline aborted
- **WARNING** — suspicious patterns found, proceeds with caution
- **SAFE** — no threats detected

Use `--skip-security-scan` to bypass when you trust the source.

---

## Autonomy Levels

Three levels control what tools Claude Code can use, inspired by [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw). Configure via `autonomy` in `config.yaml` or toggle live with `/autonomy`.

| Level | Tools | Risk Awareness | Use Case |
|-------|-------|----------------|----------|
| `full` | Unrestricted (`--dangerously-skip-permissions`) | None | Default — trusted local use |
| `supervised` | Restricted whitelist (read + safe writes + safe bash) | Risk-tier prompting (low/medium/high) | Shared environments, demo mode |
| `readonly` | Read-only (Read, Glob, Grep, WebFetch, Task) | N/A | Research-only, audit mode |

---

## Additional Controls

All configured in `config.yaml`, all hot-reload on next message:

| Setting | Purpose |
|---------|---------|
| `forbidden_paths` | Directories the agent must never access (e.g., `~/.ssh`, `~/.aws`) |
| `security.filesystem_scoping` | Allowed directory prefixes (empty = allow all) |
| `security.block_symlink_escape` | Prevents symlinks from escaping filesystem scope |
| `security.deny_by_default` | When `true`, empty `allowed_users` list = deny all users |

---

## Safety Gates Summary

- Automated security scanner on all external code
- Skills queue with human `/approve` gate — never auto-installs
- Daily + weekly cost caps enforced before every Claude invocation
- User whitelisting on all platforms
- Review agent validation in `/evolve` pipeline
- Bounded memory limits (hard character caps)
- Deny-by-default auth on all platforms
- Filesystem scoping and forbidden paths
