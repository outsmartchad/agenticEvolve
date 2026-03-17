"""Self-audit / doctor — diagnose system health and security.

Adapted from OpenClaw's audit.ts and doctor.ts. Provides:
- Security checks (env permissions, config exposure, secrets in files)
- Runtime health checks (Docker, whisper, dependencies)
- Configuration validation
- Database integrity
"""
import logging
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("agenticEvolve.self_audit")

EXODIR = Path.home() / ".agenticEvolve"


class Severity:
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class Finding:
    check_id: str
    severity: str
    title: str
    detail: str
    remediation: str = ""


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)
    critical: int = 0
    warn: int = 0
    info: int = 0

    def add(self, finding: Finding):
        self.findings.append(finding)
        if finding.severity == Severity.CRITICAL:
            self.critical += 1
        elif finding.severity == Severity.WARN:
            self.warn += 1
        else:
            self.info += 1

    def summary(self) -> str:
        total = len(self.findings)
        return (
            f"Audit: {total} findings "
            f"({self.critical} critical, {self.warn} warn, {self.info} info)"
        )

    def format_text(self) -> str:
        lines = [self.summary(), ""]
        for f in self.findings:
            icon = {"critical": "!!!", "warn": "!!", "info": "i"}.get(f.severity, "?")
            lines.append(f"[{icon}] {f.title}")
            lines.append(f"    {f.detail}")
            if f.remediation:
                lines.append(f"    Fix: {f.remediation}")
            lines.append("")
        return "\n".join(lines)


# ── Security Checks ──────────────────────────────────────────

def _check_env_file(report: AuditReport):
    """Check .env file permissions."""
    env_file = EXODIR / ".env"
    if not env_file.exists():
        env_file = Path.cwd() / ".env"
    if not env_file.exists():
        report.add(Finding(
            "env.missing", Severity.INFO,
            ".env file not found",
            "No .env file at ~/.agenticEvolve/.env or cwd",
        ))
        return

    mode = env_file.stat().st_mode
    if mode & stat.S_IROTH or mode & stat.S_IWOTH:
        report.add(Finding(
            "env.world_readable", Severity.CRITICAL,
            ".env file is world-readable",
            f"{env_file} has permissions {oct(mode)[-3:]}",
            f"chmod 600 {env_file}",
        ))
    else:
        report.add(Finding(
            "env.ok", Severity.INFO,
            ".env file permissions OK",
            f"{env_file} permissions: {oct(mode)[-3:]}",
        ))


def _check_config_secrets(report: AuditReport):
    """Check if config.yaml contains secrets."""
    from .redact import DEFAULT_PATTERNS
    config_file = EXODIR / "config.yaml"
    if not config_file.exists():
        config_file = Path.cwd() / "config.yaml"
    if not config_file.exists():
        return

    try:
        content = config_file.read_text()
        for pattern in DEFAULT_PATTERNS:
            if pattern.search(content):
                report.add(Finding(
                    "config.secrets", Severity.WARN,
                    "Potential secrets in config.yaml",
                    "config.yaml may contain API keys or tokens. Use .env instead.",
                    "Move secrets to .env and reference via environment variables",
                ))
                return
    except Exception:
        pass


def _check_allowed_users(report: AuditReport, config: dict):
    """Check allowed_users configuration."""
    platforms = config.get("platforms", {})
    for name, pcfg in platforms.items():
        if not pcfg.get("enabled"):
            continue
        users = pcfg.get("allowed_users", [])
        deny_default = config.get("security", {}).get("deny_by_default", False)
        if not users and not deny_default:
            report.add(Finding(
                f"auth.{name}.open", Severity.WARN,
                f"{name}: no allowed_users and deny_by_default=false",
                "Anyone can interact with the bot on this platform",
                f"Add user IDs to platforms.{name}.allowed_users or set security.deny_by_default: true",
            ))


def _check_cost_caps(report: AuditReport, config: dict):
    """Check cost cap configuration."""
    daily = config.get("daily_cost_cap", 999999)
    weekly = config.get("weekly_cost_cap", 999999)
    if daily >= 100:
        report.add(Finding(
            "cost.daily_high", Severity.WARN,
            f"Daily cost cap is very high: ${daily}",
            "Effectively unlimited spending. A runaway session could be expensive.",
            "Set daily_cost_cap to a reasonable value (e.g., 10-50)",
        ))
    if weekly >= 500:
        report.add(Finding(
            "cost.weekly_high", Severity.WARN,
            f"Weekly cost cap is very high: ${weekly}",
            "Effectively unlimited weekly spending.",
            "Set weekly_cost_cap to a reasonable value (e.g., 50-200)",
        ))


# ── Runtime Health Checks ────────────────────────────────────

def _check_dependencies(report: AuditReport):
    """Check required binaries."""
    deps = {
        "claude": "Claude CLI (core agent engine)",
        "ffmpeg": "Audio/video processing",
        "ffprobe": "Audio duration detection",
    }
    optional_deps = {
        "whisper-cli": "Local STT (brew install whisper-cpp)",
        "docker": "Sandbox execution",
    }

    for cmd, desc in deps.items():
        if shutil.which(cmd):
            report.add(Finding(f"dep.{cmd}.ok", Severity.INFO, f"{cmd}: installed", desc))
        else:
            report.add(Finding(
                f"dep.{cmd}.missing", Severity.CRITICAL,
                f"{cmd}: NOT FOUND",
                f"{desc} — required for operation",
                f"Install {cmd}",
            ))

    for cmd, desc in optional_deps.items():
        if shutil.which(cmd):
            report.add(Finding(f"dep.{cmd}.ok", Severity.INFO, f"{cmd}: installed", desc))
        else:
            report.add(Finding(f"dep.{cmd}.missing", Severity.INFO, f"{cmd}: not installed", desc))


def _check_whisper_model(report: AuditReport):
    """Check whisper model availability."""
    models_dir = EXODIR / "models"
    model_files = list(models_dir.glob("ggml-*.bin")) if models_dir.exists() else []
    if model_files:
        names = [f.name for f in model_files]
        sizes = sum(f.stat().st_size for f in model_files)
        report.add(Finding(
            "whisper.model.ok", Severity.INFO,
            f"Whisper models: {', '.join(names)} ({sizes / 1e6:.0f}MB)",
            "Local STT available",
        ))
    else:
        report.add(Finding(
            "whisper.model.missing", Severity.WARN,
            "No whisper model found",
            f"No ggml-*.bin in {models_dir}",
            "Download: curl -L -o ~/.agenticEvolve/models/ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
        ))


def _check_sandbox(report: AuditReport, config: dict):
    """Check Docker sandbox health."""
    sandbox_cfg = config.get("sandbox", {})
    if not sandbox_cfg.get("enabled"):
        report.add(Finding("sandbox.disabled", Severity.INFO, "Sandbox: disabled", "Docker sandbox not enabled in config"))
        return

    if not shutil.which("docker"):
        report.add(Finding(
            "sandbox.no_docker", Severity.WARN,
            "Sandbox enabled but Docker not installed",
            "sandbox.enabled=true but docker binary not found",
            "Install Docker or set sandbox.enabled: false",
        ))
        return

    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=ae-sandbox", "--format", "{{.Names}}"],
            capture_output=True, timeout=10,
        )
        containers = result.stdout.decode().strip().splitlines()
        if containers:
            report.add(Finding("sandbox.ok", Severity.INFO, f"Sandbox: {len(containers)} container(s) running", ", ".join(containers)))
        else:
            report.add(Finding("sandbox.no_container", Severity.WARN, "Sandbox: no containers running", "sandbox.enabled=true but no ae-sandbox container"))
    except Exception as e:
        report.add(Finding("sandbox.error", Severity.WARN, f"Sandbox check failed: {e}", "Could not query Docker"))


def _check_session_db(report: AuditReport):
    """Check session database integrity."""
    db_path = EXODIR / "sessions.db"
    if not db_path.exists():
        report.add(Finding("db.missing", Severity.INFO, "Session DB not found", "Will be created on first run"))
        return

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            size = db_path.stat().st_size / 1e6
            report.add(Finding("db.ok", Severity.INFO, f"Session DB: OK ({size:.1f}MB)", "Integrity check passed"))
        else:
            report.add(Finding("db.corrupt", Severity.CRITICAL, "Session DB: CORRUPT", f"Integrity check: {result}", "Backup and recreate: mv sessions.db sessions.db.bak"))
    except Exception as e:
        report.add(Finding("db.error", Severity.WARN, f"Session DB check failed: {e}", str(e)))


# ── Main Audit Function ──────────────────────────────────────

def run_audit(config: dict | None = None) -> AuditReport:
    """Run all diagnostic checks. Returns an AuditReport."""
    if config is None:
        try:
            from .config import load_config
            config = load_config()
        except Exception:
            config = {}

    report = AuditReport()

    # Security
    _check_env_file(report)
    _check_config_secrets(report)
    _check_allowed_users(report, config)
    _check_cost_caps(report, config)

    # Runtime
    _check_dependencies(report)
    _check_whisper_model(report)
    _check_sandbox(report, config)
    _check_session_db(report)

    log.info(report.summary())
    return report
