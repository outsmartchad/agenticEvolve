---
name: security-scan
description: Scan Claude Code configuration (.claude/ directory) for security vulnerabilities, misconfigurations, and injection risks using AgentShield (1282 tests, 102 rules). Checks CLAUDE.md, settings.json, MCP servers, hooks, and agent definitions. Use when setting up new projects, after modifying Claude Code configs, before committing config changes, onboarding to a new repo, periodic security hygiene, or when the user says "is my Claude Code config secure", "scan for vulnerabilities", "audit my setup".
---

# Security Scan

Audit your Claude Code configuration for security issues using AgentShield — a static analysis tool with 1282 tests and 102 rules built at the Anthropic hackathon.

## What It Scans

| File | Checks |
|------|--------|
| `CLAUDE.md` | Hardcoded secrets, auto-run instructions, prompt injection vectors |
| `settings.json` | Overly permissive allows (e.g., `Bash(*)`), missing deny lists, dangerous bypasses |
| `mcp.json` | Risky MCP servers, hardcoded env secrets, npx supply chain risks |
| `hooks/` | Command injection via `${file}` interpolation, data exfiltration, silent error swallowing |
| `agents/*.md` | Unrestricted tool access, prompt injection surface area |

## Usage

```bash
# Quick scan (no install needed)
npx ecc-agentshield scan

# Scan specific path
npx ecc-agentshield scan --path /path/to/.claude

# Filter by severity
npx ecc-agentshield scan --min-severity medium

# JSON output for CI/CD pipelines
npx ecc-agentshield scan --format json

# Auto-fix safe issues
npx ecc-agentshield scan --fix

# Deep analysis with three Opus agents (red-team/blue-team/auditor)
npx ecc-agentshield scan --opus --stream

# Generate secure config from scratch
npx ecc-agentshield init
```

## The `--opus` Flag

Runs three Claude Opus agents in a red-team/blue-team/auditor pipeline:
1. **Attacker** finds exploit chains in your config
2. **Defender** evaluates existing protections
3. **Auditor** synthesizes both into a prioritized risk assessment

This is adversarial reasoning, not just pattern matching.

## Severity Levels

| Grade | Score | Meaning |
|-------|-------|---------|
| A | 90-100 | Secure configuration |
| B | 75-89 | Minor issues worth fixing |
| C | 60-74 | Needs attention |
| D | 40-59 | Significant risks |
| F | 0-39 | Critical vulnerabilities — fix immediately |

## Critical Findings (fix immediately)
- Hardcoded API keys in config files
- `Bash(*)` in allow list (allows arbitrary command execution)
- Command injection in hooks via `${file}` interpolation
- Shell-running MCP servers without sandboxing

## High Findings (fix before production use)
- Auto-run instructions in CLAUDE.md
- Missing deny lists for dangerous operations
- Agents with unnecessary Bash access
- MCP servers with hardcoded credentials

## GitHub Action

```yaml
- uses: affaan-m/agentshield@v1
  with:
    path: '.'
    min-severity: 'medium'
    fail-on-findings: true
```

Source: [AgentShield](https://github.com/affaan-m/agentshield) from [everything-claude-code](https://github.com/affaan-m/everything-claude-code)
