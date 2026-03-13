"""Autonomy level enforcement for Claude Code invocations.

Inspired by ZeroClaw's autonomy levels pattern:
  - "readonly"   → only read tools, no writes, no bash
  - "supervised" → allowed_tools whitelist, restricted bash
  - "full"       → --dangerously-skip-permissions (current default)

Maps autonomy config to Claude Code CLI flags (--allowedTools vs
--dangerously-skip-permissions) and injects filesystem scoping rules
into the system prompt.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger("agenticEvolve.autonomy")

# Default tool sets per autonomy level
READONLY_TOOLS = [
    "Read", "Glob", "Grep", "WebFetch", "Task",
]

SUPERVISED_TOOLS = [
    "Read", "Glob", "Grep", "WebFetch", "Task",
    "Write", "Edit",
    "Bash(git status)", "Bash(git diff)", "Bash(git log)",
    "Bash(ls)", "Bash(cat)", "Bash(head)", "Bash(tail)",
    "Bash(python)", "Bash(node)", "Bash(npm test)", "Bash(npm run)",
    "Bash(pytest)",
]


def resolve_tools(config: dict) -> list[str] | None:
    """Resolve the tool allowlist from config autonomy level.

    Returns:
        list[str] for --allowedTools, or None for --dangerously-skip-permissions
    """
    autonomy = config.get("autonomy", "full")
    explicit_tools = config.get("allowed_tools", [])

    if explicit_tools:
        # Explicit override takes precedence over autonomy level
        log.debug(f"Autonomy: explicit allowed_tools ({len(explicit_tools)} tools)")
        return explicit_tools

    if autonomy == "readonly":
        log.debug("Autonomy: readonly — read-only tools only")
        return READONLY_TOOLS
    elif autonomy == "supervised":
        log.debug("Autonomy: supervised — restricted tool set")
        return SUPERVISED_TOOLS
    elif autonomy == "full":
        return None  # --dangerously-skip-permissions
    else:
        log.warning(f"Unknown autonomy level '{autonomy}', defaulting to 'full'")
        return None


def build_filesystem_rules(config: dict) -> str:
    """Build filesystem scoping rules for system prompt injection.

    Returns a string to append to the system prompt, or empty string
    if no restrictions apply.
    """
    parts = []

    forbidden_paths = config.get("forbidden_paths", [])
    if forbidden_paths:
        expanded = [os.path.expanduser(p) for p in forbidden_paths]
        parts.append(
            "# FORBIDDEN PATHS (never read, write, or reference these):\n"
            + "\n".join(f"- {p}" for p in expanded)
        )

    security = config.get("security", {})
    scoping = security.get("filesystem_scoping", [])
    if scoping:
        expanded = [os.path.expanduser(p) for p in scoping]
        parts.append(
            "# FILESYSTEM SCOPE (only operate within these directories):\n"
            + "\n".join(f"- {p}" for p in expanded)
            + "\nDo NOT read or write files outside these directories."
        )

    if security.get("block_symlink_escape", True) and (scoping or forbidden_paths):
        parts.append(
            "# SYMLINK SAFETY: Before following any symlink, verify its real "
            "path (readlink -f) stays within the allowed filesystem scope. "
            "Do NOT follow symlinks that escape to forbidden or out-of-scope paths."
        )

    return "\n\n".join(parts)


def check_path_allowed(filepath: str, config: dict) -> tuple[bool, str]:
    """Check if a file path is allowed by the current security config.

    Returns (allowed, reason).
    """
    resolved = Path(filepath).resolve()

    # Check forbidden paths
    forbidden = config.get("forbidden_paths", [])
    for fp in forbidden:
        fp_resolved = Path(os.path.expanduser(fp)).resolve()
        try:
            resolved.relative_to(fp_resolved)
            return False, f"Path is forbidden: {fp}"
        except ValueError:
            pass

    # Check filesystem scoping
    security = config.get("security", {})
    scoping = security.get("filesystem_scoping", [])
    if scoping:
        allowed = False
        for sp in scoping:
            sp_resolved = Path(os.path.expanduser(sp)).resolve()
            try:
                resolved.relative_to(sp_resolved)
                allowed = True
                break
            except ValueError:
                pass
        if not allowed:
            return False, f"Path outside filesystem scope: {resolved}"

    # Symlink escape detection
    if security.get("block_symlink_escape", True) and scoping:
        real_path = Path(filepath).resolve()
        if real_path != resolved:
            # This is a symlink — check that resolved path is within scope
            in_scope = False
            for sp in scoping:
                sp_resolved = Path(os.path.expanduser(sp)).resolve()
                try:
                    real_path.relative_to(sp_resolved)
                    in_scope = True
                    break
                except ValueError:
                    pass
            if not in_scope:
                return False, f"Symlink escapes filesystem scope: {filepath} -> {real_path}"

    return True, ""


# ── Risk tier classification (ZeroClaw pattern) ─────────────────

RISK_TIERS = {
    "low": {
        "description": "Read-only operations, no side effects",
        "examples": ["Read", "Glob", "Grep", "WebFetch", "git status", "git log", "git diff", "ls", "cat"],
        "validation": "none",
    },
    "medium": {
        "description": "Write operations within allowed scope",
        "examples": ["Write", "Edit", "git add", "git commit", "mkdir", "npm install", "pip install"],
        "validation": "auto-approved in full/supervised mode",
    },
    "high": {
        "description": "Destructive or external-facing operations",
        "examples": ["rm -rf", "git push", "git reset --hard", "curl -X POST", "chmod", "docker", "deploy"],
        "validation": "requires confirmation in supervised mode, blocked in readonly",
    },
}


def build_risk_awareness_prompt(config: dict) -> str:
    """Build risk tier awareness instructions for the system prompt.

    Only injected in 'supervised' mode — in 'full' mode Claude already has
    unrestricted access, in 'readonly' the tool whitelist handles it.
    """
    autonomy = config.get("autonomy", "full")
    if autonomy != "supervised":
        return ""

    return (
        "# RISK TIER CLASSIFICATION\n"
        "Before executing any tool, classify it by risk level:\n\n"
        "LOW RISK (auto-approve): Read, Glob, Grep, WebFetch, git status/log/diff, ls, cat\n"
        "MEDIUM RISK (proceed with note): Write, Edit, git add/commit, mkdir, npm/pip install\n"
        "HIGH RISK (state risk before proceeding): rm, git push/reset, curl POST, chmod, "
        "docker, deploy, any operation that deletes data or communicates externally\n\n"
        "For HIGH RISK operations: explicitly state what you're about to do and why "
        "before executing. If the operation is destructive, warn the user first."
    )


def format_autonomy_status(config: dict) -> str:
    """Format current autonomy settings for display (e.g. /status command)."""
    autonomy = config.get("autonomy", "full")
    forbidden = config.get("forbidden_paths", [])
    security = config.get("security", {})
    scoping = security.get("filesystem_scoping", [])
    deny_default = security.get("deny_by_default", False)

    lines = [f"Autonomy: {autonomy}"]

    if autonomy == "readonly":
        lines.append("  Tools: read-only (no writes, no bash)")
    elif autonomy == "supervised":
        lines.append("  Tools: restricted (safe bash only)")
    else:
        lines.append("  Tools: unrestricted")

    explicit = config.get("allowed_tools", [])
    if explicit:
        lines.append(f"  Custom tools: {len(explicit)} whitelisted")

    if forbidden:
        lines.append(f"  Forbidden paths: {len(forbidden)}")
    if scoping:
        lines.append(f"  Filesystem scope: {len(scoping)} allowed dirs")
    if deny_default:
        lines.append("  Deny-by-default: enabled")

    return "\n".join(lines)
