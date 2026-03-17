"""Exec allowlist — command approval system for gateway execution mode.

When exec.mode is "gateway" (host execution without Docker sandbox),
commands are evaluated against an allowlist + safe_bins + denylist.

Inspired by OpenClaw's exec-approvals.ts pattern:
  - Persistent allowlist stored in JSON file
  - Safe bins auto-approved (ls, git, python3, etc.)
  - Denylist regex patterns always block
  - Three security levels: deny, allowlist, full
  - Three ask modes: off, on-miss, always

Config (config.yaml):
    exec:
        mode: sandbox           # sandbox | gateway
        security: allowlist     # deny | allowlist | full
        ask: on-miss            # off | on-miss | always
        ask_timeout: 120        # seconds to wait for approval
        safe_bins:              # auto-approved commands
            - ls
            - cat
            - git
            - python3
            - node
        denied_patterns:        # regex denylist (always block)
            - "rm -rf /"
            - "curl.*\\|.*sh"
"""
import json
import logging
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Optional

log = logging.getLogger("agenticEvolve.exec_allowlist")

EXODIR = Path.home() / ".agenticEvolve"
ALLOWLIST_FILE = EXODIR / "exec-allowlist.json"

# Default safe binaries — commands auto-allowed without explicit approval
DEFAULT_SAFE_BINS = frozenset({
    "ls", "cat", "head", "tail", "wc", "sort", "uniq", "tr", "cut",
    "echo", "printf", "true", "false", "test", "[",
    "grep", "rg", "find", "fd", "which", "whereis", "file", "stat",
    "pwd", "basename", "dirname", "readlink", "realpath",
    "date", "cal", "env", "printenv", "uname", "hostname",
    "git", "gh",
    "python3", "python", "pip", "pip3",
    "node", "npm", "npx", "yarn", "pnpm", "bun",
    "cargo", "rustc",
    "go",
    "docker", "docker-compose",
    "make", "cmake",
    "jq", "yq",
    "curl", "wget",  # allowed but denylist catches dangerous pipe patterns
    "ssh", "scp",
    "tar", "zip", "unzip", "gzip", "gunzip",
    "diff", "patch",
    "tee", "xargs",
    "sed", "awk",
    "mkdir", "touch", "cp", "mv", "ln",
    "chmod", "chown",
})

# Default denylist — regex patterns that ALWAYS block
DEFAULT_DENIED_PATTERNS = [
    r"rm\s+-rf\s+/\s*$",               # rm -rf /
    r"rm\s+-rf\s+/\*",                  # rm -rf /*
    r"rm\s+-rf\s+~\s*$",               # rm -rf ~
    r"mkfs\.",                           # mkfs.* (format disk)
    r"dd\s+if=.*of=/dev/",             # dd to disk device
    r":\(\)\{.*\}",                     # fork bomb
    r"curl.*\|\s*sh",                   # curl | sh
    r"curl.*\|\s*bash",                 # curl | bash
    r"wget.*\|\s*sh",                   # wget | sh
    r"eval.*base64",                    # base64 decode to eval
    r"python.*-c.*exec\(.*base64",     # python exec base64
    r">\s*/etc/",                       # overwrite system config
    r">\s*/dev/",                       # write to devices
]


@dataclass
class AllowlistEntry:
    """A persistent allowlist entry for an approved command pattern."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    pattern: str = ""               # binary name or path glob
    added_at: float = field(default_factory=time.time)
    added_by: str = ""              # user who approved
    last_used_at: Optional[float] = None
    last_command: str = ""          # last full command that matched
    use_count: int = 0


@dataclass
class EvalResult:
    """Result of evaluating a command against the allowlist."""
    allowed: bool
    reason: str
    needs_approval: bool = False    # requires user approval before executing
    matched_entry: Optional[AllowlistEntry] = None
    blocked_by: str = ""            # denylist pattern that blocked


class ExecAllowlist:
    """Command allowlist manager for gateway exec mode."""

    def __init__(self, config: dict | None = None):
        cfg = (config or {}).get("exec", {})
        self.security: str = cfg.get("security", "allowlist")
        self.ask: str = cfg.get("ask", "on-miss")
        self.ask_timeout: int = cfg.get("ask_timeout", 120)

        # Build safe bins set from config + defaults
        custom_safe = cfg.get("safe_bins", [])
        self.safe_bins: set[str] = set(DEFAULT_SAFE_BINS)
        if custom_safe:
            self.safe_bins.update(custom_safe)

        # Build deny patterns from config + defaults
        custom_denied = cfg.get("denied_patterns", [])
        self.denied_patterns: list[re.Pattern] = []
        for pat in DEFAULT_DENIED_PATTERNS + custom_denied:
            try:
                self.denied_patterns.append(re.compile(pat, re.IGNORECASE))
            except re.error:
                log.warning(f"Invalid denylist regex: {pat}")

        # Load persistent allowlist
        self._entries: list[AllowlistEntry] = self._load()

    def _load(self) -> list[AllowlistEntry]:
        """Load allowlist from JSON file."""
        if not ALLOWLIST_FILE.exists():
            return []
        try:
            data = json.loads(ALLOWLIST_FILE.read_text())
            return [AllowlistEntry(**e) for e in data]
        except Exception as e:
            log.warning(f"Failed to load exec allowlist: {e}")
            return []

    def _save(self):
        """Persist allowlist to JSON file."""
        try:
            ALLOWLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(e) for e in self._entries]
            ALLOWLIST_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Failed to save exec allowlist: {e}")

    def _extract_binary(self, command: str) -> str:
        """Extract the primary binary name from a command string.

        Handles pipes, chains, and common prefixes.
        """
        # Strip leading env vars (VAR=val cmd)
        cmd = command.strip()
        while re.match(r'^[A-Z_][A-Z0-9_]*=\S+\s+', cmd):
            cmd = re.sub(r'^[A-Z_][A-Z0-9_]*=\S+\s+', '', cmd, count=1)

        # Take first segment before pipes/chains
        for sep in ["|", "&&", "||", ";"]:
            cmd = cmd.split(sep)[0].strip()

        # Strip sudo prefix
        if cmd.startswith("sudo "):
            cmd = cmd[5:].strip()

        # Extract binary (first word)
        binary = cmd.split()[0] if cmd.split() else ""

        # Resolve to basename
        return os.path.basename(binary)

    def _check_denylist(self, command: str) -> Optional[str]:
        """Check if command matches any denylist pattern.

        Returns the matching pattern string if blocked, None if OK.
        """
        for pat in self.denied_patterns:
            if pat.search(command):
                return pat.pattern
        return None

    def _check_safe_bin(self, binary: str) -> bool:
        """Check if binary is in the safe bins list."""
        return binary in self.safe_bins

    def _check_allowlist(self, binary: str) -> Optional[AllowlistEntry]:
        """Check if binary matches an allowlist entry."""
        for entry in self._entries:
            if entry.pattern == binary or entry.pattern == "*":
                return entry
            # Glob-style matching
            if re.match(entry.pattern.replace("*", ".*"), binary):
                return entry
        return None

    def evaluate(self, command: str) -> EvalResult:
        """Evaluate a command against the security layers.

        Returns an EvalResult indicating whether the command is allowed,
        needs approval, or is blocked.
        """
        # Security level: deny = block everything
        if self.security == "deny":
            return EvalResult(
                allowed=False,
                reason="Execution disabled (security=deny)")

        # Security level: full = allow everything (but still check denylist)
        if self.security == "full":
            denied = self._check_denylist(command)
            if denied:
                return EvalResult(
                    allowed=False,
                    reason=f"Blocked by denylist pattern: {denied}",
                    blocked_by=denied)
            return EvalResult(allowed=True, reason="Full access mode")

        # Security level: allowlist
        # Step 1: Always check denylist first
        denied = self._check_denylist(command)
        if denied:
            return EvalResult(
                allowed=False,
                reason=f"Blocked by denylist pattern: {denied}",
                blocked_by=denied)

        # Step 2: Extract binary and check safe bins
        binary = self._extract_binary(command)
        if not binary:
            return EvalResult(
                allowed=False,
                reason="Could not determine command binary")

        if self._check_safe_bin(binary):
            return EvalResult(
                allowed=True,
                reason=f"Safe binary: {binary}")

        # Step 3: Check persistent allowlist
        entry = self._check_allowlist(binary)
        if entry:
            # Update usage stats
            entry.last_used_at = time.time()
            entry.last_command = command[:200]
            entry.use_count += 1
            self._save()
            return EvalResult(
                allowed=True,
                reason=f"Allowlist match: {entry.pattern}",
                matched_entry=entry)

        # Step 4: Check ask mode
        if self.ask == "off":
            return EvalResult(
                allowed=False,
                reason=f"Not in allowlist: {binary} (ask=off)")
        elif self.ask == "always":
            return EvalResult(
                allowed=False,
                needs_approval=True,
                reason=f"Approval required (ask=always): {binary}")
        else:  # on-miss
            return EvalResult(
                allowed=False,
                needs_approval=True,
                reason=f"Not in allowlist, approval needed: {binary}")

    def add_entry(self, pattern: str, added_by: str = "") -> AllowlistEntry:
        """Add a new allowlist entry."""
        entry = AllowlistEntry(pattern=pattern, added_by=added_by)
        self._entries.append(entry)
        self._save()
        log.info(f"Exec allowlist: added '{pattern}' by {added_by}")
        return entry

    def remove_entry(self, entry_id: str) -> bool:
        """Remove an allowlist entry by ID."""
        for i, entry in enumerate(self._entries):
            if entry.id == entry_id:
                removed = self._entries.pop(i)
                self._save()
                log.info(f"Exec allowlist: removed '{removed.pattern}'")
                return True
        return False

    def list_entries(self) -> list[AllowlistEntry]:
        """Return all allowlist entries."""
        return list(self._entries)

    def add_from_command(self, command: str, added_by: str = "") -> AllowlistEntry:
        """Add an allowlist entry derived from a command's binary."""
        binary = self._extract_binary(command)
        return self.add_entry(binary, added_by)
