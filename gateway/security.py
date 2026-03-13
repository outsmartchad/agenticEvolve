"""Security scanner for external repos and code before absorb/learn/evolve.

Scans cloned repos and generated files for:
  - Credential exfiltration (reading ~/.ssh, ~/.aws, keychain, .env files)
  - Reverse shells / network backdoors
  - Malicious install scripts (postinstall, preinstall hooks)
  - Obfuscated code (base64 decode + eval, hex-encoded payloads)
  - Destructive commands (rm -rf /, disk wipe, etc.)
  - Cryptocurrency miners
  - Sensitive file access on macOS (Keychain, login items, LaunchAgents)

Returns a verdict: SAFE / WARNING / BLOCKED with detailed findings.
"""
import logging
import os
import re
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger("agenticEvolve.security")

# ── Pattern definitions ──────────────────────────────────────────

# Critical: immediately block
CRITICAL_PATTERNS = [
    # Credential / secret exfiltration
    (r'(cat|less|head|tail|cp|scp|curl.*-d.*@|rsync)\s+.*~/?\.(ssh|aws|gnupg|config/gcloud)', "Reading SSH/AWS/GnuPG/GCloud credentials"),
    (r'(cat|cp|curl.*-d|base64)\s+.*/etc/(passwd|shadow)', "Reading system password files"),
    (r'security\s+find-(generic-password|internet-password)', "macOS Keychain credential extraction"),
    (r'security\s+dump-keychain', "macOS Keychain dump"),
    (r'(curl|wget|nc|ncat)\s+.*\|\s*(ba)?sh', "Remote code execution via pipe to shell"),
    (r'(curl|wget).*(-o|>)\s*/tmp/.*&&.*(chmod|bash|sh|\.\/)', "Download and execute pattern"),
    (r'(bash|sh|python|perl|ruby)\s+-c\s+.*\$\(curl', "Inline remote code execution"),

    # Reverse shells
    (r'(bash|sh)\s+-i\s+>&?\s*/dev/tcp/', "Bash reverse shell"),
    (r'nc\s+-e\s+/bin/(ba)?sh', "Netcat reverse shell"),
    (r'python.*socket.*connect.*subprocess', "Python reverse shell pattern"),
    (r'mkfifo\s+/tmp/.*\|\s*/bin/(ba)?sh', "Named pipe reverse shell"),
    (r'exec\s+\d+<>/dev/tcp/', "File descriptor reverse shell"),

    # Obfuscated execution
    (r'eval\s*\(\s*(atob|Buffer\.from|base64.*decode)', "Eval of base64-decoded payload"),
    (r'echo\s+[A-Za-z0-9+/=]{50,}\s*\|\s*base64\s+-d\s*\|\s*(ba)?sh', "Base64-encoded shell command"),
    (r'python.*-c.*exec\(.*decode\(', "Python obfuscated exec"),
    (r'\\x[0-9a-fA-F]{2}(\\x[0-9a-fA-F]{2}){10,}', "Hex-encoded payload (>10 bytes)"),

    # Destructive
    (r'rm\s+-rf\s+(/|~/|\$HOME/?\s)', "Destructive rm -rf on home/root"),
    (r'dd\s+if=/dev/(zero|random)\s+of=/dev/', "Disk wipe via dd"),
    (r'mkfs\.\w+\s+/dev/', "Filesystem format"),
    (r':(){ :\|:& };:', "Fork bomb"),

    # Cryptocurrency miners
    (r'(xmrig|minerd|cpuminer|stratum\+tcp://)', "Cryptocurrency miner"),

    # macOS persistence / privilege escalation
    (r'(LaunchAgents|LaunchDaemons)/.*\.plist', "macOS LaunchAgent/Daemon persistence"),
    (r'osascript\s+-e.*admin', "macOS AppleScript privilege escalation"),
    (r'defaults\s+write.*LoginItems', "macOS login item persistence"),
    (r'tccutil\s+reset', "macOS TCC permission reset"),
]

# Warning: flag but don't block
WARNING_PATTERNS = [
    # Suspicious network activity
    (r'(curl|wget|fetch)\s+https?://\d+\.\d+\.\d+\.\d+', "HTTP request to raw IP address"),
    (r'(curl|wget).*(-X\s+POST|-d\s+)', "HTTP POST with data (potential exfiltration)"),
    (r'nc\s+-l', "Netcat listener"),

    # Sensitive file access
    (r'(cat|read|open)\s+.*\.(env|pem|key|p12|pfx|jks)', "Reading sensitive credential files"),
    (r'(cat|read|open)\s+.*/\.agenticEvolve/(\.env|config\.yaml)', "Reading agenticEvolve secrets"),
    (r'(ANTHROPIC_API_KEY|OPENAI_API_KEY|TELEGRAM_BOT_TOKEN|AWS_SECRET)', "References API key environment variable"),

    # Package manager hooks
    (r'"(pre|post)(install|build|publish)":\s*"', "npm lifecycle script hook"),
    (r'setup\(\s*[^)]*cmdclass', "Python setup.py custom command class"),
    (r'subprocess\.(run|call|Popen)\s*\(', "subprocess execution in Python"),

    # Dynamic code execution
    (r'\beval\s*\(', "eval() usage"),
    (r'\bexec\s*\(', "exec() usage"),
    (r'__import__\s*\(', "Dynamic import"),
    (r'importlib\.import_module', "Dynamic module import"),
    (r'os\.system\s*\(', "os.system() call"),

    # File system manipulation
    (r'shutil\.rmtree\s*\(', "Recursive directory deletion"),
    (r'os\.(remove|unlink|rmdir)\s*\(', "File deletion"),
    (r'chmod\s+[0-7]*7[0-7]*\s', "World-writable permissions"),
]

# Prompt injection patterns — checked only for doc/text files to avoid false positives
PROMPT_INJECTION_PATTERNS = [
    (r'ignore (all )?(prior|previous|above) instructions', "Potential prompt injection: ignore instructions"),
    (r'disregard (all )?(prior|previous|above)', "Potential prompt injection: disregard instructions"),
    (r'you are now [a-z]', "Potential prompt injection: persona reassignment"),
    (r'act as (a |an )?[a-z]', "Potential prompt injection: role override"),
    (r'new (system )?prompt[:\s]', "Potential prompt injection: system prompt override"),
    (r'<\s*(system|instructions?)\s*>', "Potential prompt injection: XML system tag"),
    (r'STOP[.\s]+FROM NOW ON', "Potential prompt injection: instruction override"),
]

# Doc/text file extensions subject to prompt injection checks
PROMPT_INJECTION_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".rst"}

# Files that should always be checked more carefully
SUSPICIOUS_FILENAMES = [
    "postinstall", "preinstall", "postbuild", "prebuild",
    ".postinstall.js", ".preinstall.js",
    "setup.py", "setup.cfg",
    "Makefile", "GNUmakefile",
    "install.sh", "bootstrap.sh", "init.sh", "setup.sh",
    ".bashrc", ".zshrc", ".profile", ".bash_profile",
]

# File extensions to scan (skip binaries, images, etc.)
SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".bash", ".zsh",
    ".rb", ".pl", ".php", ".go", ".rs", ".c", ".cpp", ".h",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".env", ".plist", ".xml",
    "",  # extensionless files (scripts, Makefile, etc.)
}

# Max file size to scan (skip huge files)
MAX_FILE_SIZE = 512 * 1024  # 512 KB

# Max files to scan (prevent DoS on huge repos)
MAX_FILES = 2000


class Finding(NamedTuple):
    severity: str  # "critical" or "warning"
    file: str
    line: int
    pattern_desc: str
    matched_text: str


class ScanResult(NamedTuple):
    verdict: str  # "SAFE", "WARNING", "BLOCKED"
    findings: list  # list of Finding
    files_scanned: int
    summary: str


def scan_directory(path: str | Path, label: str = "") -> ScanResult:
    """Scan a directory tree for security threats.

    Args:
        path: Directory to scan
        label: Human-readable label for reporting (e.g. repo URL)

    Returns:
        ScanResult with verdict, findings, and summary
    """
    path = Path(path)
    if not path.exists() or not path.is_dir():
        return ScanResult("SAFE", [], 0, f"Directory not found: {path}")

    findings: list[Finding] = []
    files_scanned = 0

    # Collect files to scan
    files_to_scan = []
    for root, dirs, files in os.walk(path):
        # Skip hidden dirs, node_modules, .git, etc.
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", "venv", ".venv", "dist", "build",
            ".git", ".svn", ".hg",
        )]

        for fname in files:
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            name_lower = fname.lower()

            # Check by extension or suspicious filename
            if ext in SCANNABLE_EXTENSIONS or name_lower in SUSPICIOUS_FILENAMES:
                try:
                    if fpath.stat().st_size <= MAX_FILE_SIZE:
                        files_to_scan.append(fpath)
                except OSError:
                    pass

            if len(files_to_scan) >= MAX_FILES:
                break
        if len(files_to_scan) >= MAX_FILES:
            break

    # Prioritize suspicious filenames (scan them first)
    def priority(f: Path) -> int:
        return 0 if f.name.lower() in SUSPICIOUS_FILENAMES else 1
    files_to_scan.sort(key=priority)

    # Scan each file
    for fpath in files_to_scan:
        try:
            content = fpath.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue

        files_scanned += 1
        rel_path = str(fpath.relative_to(path))

        for line_num, line in enumerate(content.split("\n"), 1):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                # Skip empty lines and comments (reduce false positives)
                # But still check — comments can contain real commands
                if len(line_stripped) < 5:
                    continue

            # Check critical patterns
            for pattern, desc in CRITICAL_PATTERNS:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    findings.append(Finding(
                        severity="critical",
                        file=rel_path,
                        line=line_num,
                        pattern_desc=desc,
                        matched_text=line_stripped[:200],
                    ))

            # Check warning patterns
            for pattern, desc in WARNING_PATTERNS:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    findings.append(Finding(
                        severity="warning",
                        file=rel_path,
                        line=line_num,
                        pattern_desc=desc,
                        matched_text=line_stripped[:200],
                    ))

            # Check prompt injection patterns — doc/text files only
            if fpath.suffix.lower() in PROMPT_INJECTION_EXTENSIONS:
                for pattern, desc in PROMPT_INJECTION_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(Finding(
                            severity="warning",
                            file=rel_path,
                            line=line_num,
                            pattern_desc=desc,
                            matched_text=line_stripped[:200],
                        ))

    # Determine verdict
    critical_count = sum(1 for f in findings if f.severity == "critical")
    warning_count = sum(1 for f in findings if f.severity == "warning")

    if critical_count > 0:
        verdict = "BLOCKED"
    elif warning_count >= 10:
        verdict = "WARNING"  # many warnings = suspicious
    elif warning_count > 0:
        verdict = "WARNING"
    else:
        verdict = "SAFE"

    # Build summary
    target_label = label or str(path)
    if verdict == "BLOCKED":
        summary = (
            f"SECURITY BLOCKED: {target_label}\n"
            f"Found {critical_count} critical threat(s) and {warning_count} warning(s) "
            f"across {files_scanned} files.\n\n"
            f"Critical findings:\n"
        )
        for f in findings:
            if f.severity == "critical":
                summary += f"  [{f.file}:{f.line}] {f.pattern_desc}\n    → {f.matched_text[:120]}\n"
        summary += "\nPipeline ABORTED. This repo may be malicious."
    elif verdict == "WARNING":
        summary = (
            f"SECURITY WARNING: {target_label}\n"
            f"Found {warning_count} warning(s) across {files_scanned} files.\n"
            f"No critical threats detected — proceeding with caution.\n\n"
            f"Warnings:\n"
        )
        # Show first 10 warnings
        shown = 0
        for f in findings:
            if f.severity == "warning" and shown < 10:
                summary += f"  [{f.file}:{f.line}] {f.pattern_desc}\n"
                shown += 1
        if warning_count > 10:
            summary += f"  ... and {warning_count - 10} more\n"
    else:
        summary = (
            f"SECURITY SCAN PASSED: {target_label}\n"
            f"Scanned {files_scanned} files — no threats detected."
        )

    injection_count = sum(
        1 for f in findings
        if f.severity == "warning" and f.pattern_desc.startswith("Potential prompt injection")
    )
    if injection_count > 0:
        summary += f"\nPrompt injection patterns detected in docs: {injection_count} occurrence(s)."

    log.info(f"[security] {verdict}: {target_label} — {critical_count} critical, {warning_count} warnings ({injection_count} injection), {files_scanned} files")
    return ScanResult(verdict, findings, files_scanned, summary)


def scan_file(path: str | Path, label: str = "") -> ScanResult:
    """Scan a single file for security threats."""
    path = Path(path)
    if not path.exists():
        return ScanResult("SAFE", [], 0, f"File not found: {path}")

    # Create a temp parent context and scan just that file
    findings: list[Finding] = []
    try:
        content = path.read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ScanResult("SAFE", [], 0, f"Cannot read: {path}")

    rel_path = label or path.name

    for line_num, line in enumerate(content.split("\n"), 1):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        for pattern, desc in CRITICAL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append(Finding("critical", rel_path, line_num, desc, line_stripped[:200]))

        for pattern, desc in WARNING_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append(Finding("warning", rel_path, line_num, desc, line_stripped[:200]))

    critical_count = sum(1 for f in findings if f.severity == "critical")
    warning_count = sum(1 for f in findings if f.severity == "warning")

    if critical_count > 0:
        verdict = "BLOCKED"
    elif warning_count > 0:
        verdict = "WARNING"
    else:
        verdict = "SAFE"

    summary = f"File scan {verdict}: {rel_path} — {critical_count} critical, {warning_count} warnings"
    return ScanResult(verdict, findings, 1, summary)


def format_telegram_report(result: ScanResult) -> str:
    """Format scan result for Telegram message."""
    if result.verdict == "BLOCKED":
        icon = "BLOCKED"
        lines = [f"*Security scan: {icon}*\n"]
        lines.append(f"Found {sum(1 for f in result.findings if f.severity == 'critical')} critical threat(s).\n")
        for f in result.findings:
            if f.severity == "critical":
                lines.append(f"  `{f.file}:{f.line}` — {f.pattern_desc}")
        lines.append(f"\nPipeline aborted for safety.")
    elif result.verdict == "WARNING":
        icon = "WARNING"
        warnings = [f for f in result.findings if f.severity == "warning"]
        lines = [f"*Security scan: {icon}*\n"]
        lines.append(f"Found {len(warnings)} warning(s), 0 critical. Proceeding with caution.\n")
        for f in warnings[:5]:
            lines.append(f"  `{f.file}:{f.line}` — {f.pattern_desc}")
        if len(warnings) > 5:
            lines.append(f"  ... +{len(warnings) - 5} more")
    else:
        lines = [f"*Security scan: PASSED* ({result.files_scanned} files scanned)"]

    return "\n".join(lines)
