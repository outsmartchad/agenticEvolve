"""Docker sandbox for safe code execution in served chats.

Provides an isolated Python environment (matplotlib, pandas, numpy, etc.)
so Claude can generate charts, run calculations, and produce files without
touching the host filesystem or network.

Architecture (sibling container pattern — same as OpenClaw):
  - Host spawns a long-lived Docker container with `sleep infinity`
  - Code execution goes through `docker exec` (NOT Docker-in-Docker)
  - A shared volume at /tmp/agenticEvolve-sandbox/ bridges output files
  - Container is reused across invocations, pruned after idle timeout
"""
import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger("agenticEvolve.sandbox")

# ── Constants ──────────────────────────────────────────────────────

SANDBOX_IMAGE = "agenticevolve-sandbox:latest"
CONTAINER_PREFIX = "ae-sandbox-"
SHARED_OUTPUT_DIR = Path("/tmp/agenticEvolve-sandbox")
IDLE_TIMEOUT_SECS = 6 * 3600  # 6 hours
CONTAINER_LABEL = "agenticevolve.sandbox"


# ── Docker availability ───────────────────────────────────────────

def is_docker_available() -> bool:
    """Check whether the docker CLI is installed and the daemon is reachable."""
    docker_path = shutil.which("docker")
    if not docker_path:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_image_built() -> bool:
    """Check if the sandbox Docker image exists locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", SANDBOX_IMAGE],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def build_image(project_root: str | None = None) -> bool:
    """Build the sandbox Docker image from Dockerfile.sandbox."""
    if project_root is None:
        # Try common locations
        for candidate in [
            Path.home() / ".agenticEvolve",
            Path.home() / "Desktop/projects/agenticEvolve",
        ]:
            if (candidate / "Dockerfile.sandbox").exists():
                project_root = str(candidate)
                break
    if not project_root or not Path(project_root, "Dockerfile.sandbox").exists():
        log.error("Cannot find Dockerfile.sandbox")
        return False

    log.info(f"Building sandbox image from {project_root}/Dockerfile.sandbox ...")
    try:
        result = subprocess.run(
            ["docker", "build", "-t", SANDBOX_IMAGE, "-f", "Dockerfile.sandbox", "."],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            log.info("Sandbox image built successfully")
            return True
        else:
            log.error(f"Sandbox image build failed: {result.stderr[-500:]}")
            return False
    except Exception as e:
        log.error(f"Sandbox image build error: {e}")
        return False


# ── Container lifecycle ────────────────────────────────────────────

def _container_name(session_key: str) -> str:
    """Generate a deterministic container name from session key."""
    h = hashlib.sha256(session_key.encode()).hexdigest()[:12]
    return f"{CONTAINER_PREFIX}{h}"


def _get_output_dir(session_key: str) -> Path:
    """Get the host-side output directory for a session's sandbox."""
    h = hashlib.sha256(session_key.encode()).hexdigest()[:12]
    d = SHARED_OUTPUT_DIR / h
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_container(session_key: str) -> tuple[str, Path]:
    """Ensure a sandbox container is running for this session.

    Returns (container_name, output_dir) or raises RuntimeError.
    """
    name = _container_name(session_key)
    output_dir = _get_output_dir(session_key)

    # Check if container already exists and is running
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "true" in result.stdout.lower():
            log.debug(f"Sandbox container {name} already running")
            # Update last-used label
            subprocess.run(
                ["docker", "container", "update", "--label",
                 f"{CONTAINER_LABEL}.last_used={int(time.time())}", name],
                capture_output=True, timeout=10,
            )
            return name, output_dir
    except Exception:
        pass

    # Remove stale container if exists but stopped
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True, timeout=10,
    )

    # Create new container
    log.info(f"Creating sandbox container {name}")
    cmd = [
        "docker", "run", "-d",
        "--name", name,
        # Security hardening
        "--network=none",              # No network access
        "--cap-drop=ALL",              # Drop all Linux capabilities
        "--security-opt", "no-new-privileges",  # Prevent privilege escalation
        "--read-only",                 # Read-only root filesystem
        "--tmpfs", "/tmp:size=100M",   # Writable /tmp (limited)
        # Shared output volume (host can read generated files)
        "-v", f"{output_dir}:/workspace/output",
        # Labels for management
        "--label", f"{CONTAINER_LABEL}=true",
        "--label", f"{CONTAINER_LABEL}.session={session_key}",
        "--label", f"{CONTAINER_LABEL}.created={int(time.time())}",
        "--label", f"{CONTAINER_LABEL}.last_used={int(time.time())}",
        # Resource limits
        "--memory=512m",
        "--cpus=1.0",
        "--pids-limit=100",
        # Image
        SANDBOX_IMAGE,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create sandbox: {result.stderr.strip()}")
        log.info(f"Sandbox container {name} created")
        return name, output_dir
    except subprocess.TimeoutExpired:
        raise RuntimeError("Sandbox container creation timed out")


def exec_in_sandbox(container_name: str, command: str,
                    timeout: int = 60) -> tuple[int, str, str]:
    """Execute a command inside the sandbox container.

    Returns (exit_code, stdout, stderr).
    """
    cmd = [
        "docker", "exec", "-i",
        "-w", "/workspace",
        container_name,
        "sh", "-c", command,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"


def destroy_container(session_key: str) -> None:
    """Stop and remove a sandbox container."""
    name = _container_name(session_key)
    try:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True, timeout=10,
        )
        log.info(f"Sandbox container {name} destroyed")
    except Exception as e:
        log.warning(f"Failed to destroy sandbox {name}: {e}")


def get_output_images(session_key: str) -> list[Path]:
    """Get all image files from the sandbox output directory."""
    output_dir = _get_output_dir(session_key)
    extensions = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
    images = []
    for f in output_dir.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            images.append(f)
    return sorted(images, key=lambda p: p.stat().st_mtime)


def clear_output(session_key: str) -> None:
    """Clear the output directory for a session."""
    output_dir = _get_output_dir(session_key)
    for f in output_dir.iterdir():
        try:
            f.unlink()
        except Exception:
            pass


# ── Pruning ────────────────────────────────────────────────────────

def prune_idle_containers() -> int:
    """Remove sandbox containers that have been idle beyond the timeout.

    Returns number of containers pruned.
    """
    try:
        result = subprocess.run(
            ["docker", "ps", "-a",
             "--filter", f"label={CONTAINER_LABEL}=true",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return 0
    except Exception:
        return 0

    names = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]
    pruned = 0
    now = int(time.time())

    for name in names:
        try:
            inspect = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{index .Config.Labels \"" + f"{CONTAINER_LABEL}.last_used" + "\"}}",
                 name],
                capture_output=True, text=True, timeout=10,
            )
            last_used = int(inspect.stdout.strip()) if inspect.stdout.strip() else 0
            if now - last_used > IDLE_TIMEOUT_SECS:
                subprocess.run(["docker", "rm", "-f", name],
                               capture_output=True, timeout=10)
                log.info(f"Pruned idle sandbox container: {name}")
                pruned += 1
        except Exception:
            continue

    # Also clean up orphaned output dirs
    if SHARED_OUTPUT_DIR.exists():
        active_hashes = set()
        for n in names:
            if n.startswith(CONTAINER_PREFIX):
                active_hashes.add(n[len(CONTAINER_PREFIX):])
        for d in SHARED_OUTPUT_DIR.iterdir():
            if d.is_dir() and d.name not in active_hashes:
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass

    return pruned


# ── Status ─────────────────────────────────────────────────────────

def sandbox_status() -> dict:
    """Get sandbox system status."""
    docker_ok = is_docker_available()
    image_ok = is_image_built() if docker_ok else False

    containers = []
    if docker_ok:
        try:
            result = subprocess.run(
                ["docker", "ps", "-a",
                 "--filter", f"label={CONTAINER_LABEL}=true",
                 "--format", "{{.Names}}\t{{.Status}}"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                if "\t" in line:
                    name, status = line.split("\t", 1)
                    containers.append({"name": name, "status": status})
        except Exception:
            pass

    return {
        "docker_available": docker_ok,
        "image_built": image_ok,
        "containers": containers,
        "output_dir": str(SHARED_OUTPUT_DIR),
    }


# ── System prompt injection ───────────────────────────────────────

def build_sandbox_prompt(container_name: str, output_dir: str) -> str:
    """Build the system prompt section that instructs Claude how to use the sandbox."""
    # Build denylist instructions from exec_allowlist
    denylist_block = ""
    try:
        from .exec_allowlist import DEFAULT_DENIED_PATTERNS
        if DEFAULT_DENIED_PATTERNS:
            deny_examples = []
            _deny_descriptions = {
                r"rm\s+-rf\s+/\s*$": "rm -rf /",
                r"rm\s+-rf\s+/\*": "rm -rf /*",
                r"rm\s+-rf\s+~\s*$": "rm -rf ~",
                r"mkfs\.": "mkfs.* (format disk)",
                r"dd\s+if=.*of=/dev/": "dd to disk device",
                r":\(\)\{.*\}": "fork bomb",
                r"curl.*\|\s*sh": "curl | sh (pipe to shell)",
                r"curl.*\|\s*bash": "curl | bash",
                r"wget.*\|\s*sh": "wget | sh",
                r"eval.*base64": "eval base64-encoded code",
                r"python.*-c.*exec\(.*base64": "python exec base64",
                r">\s*/etc/": "overwrite /etc/ files",
                r">\s*/dev/": "write to /dev/ devices",
            }
            for pat in DEFAULT_DENIED_PATTERNS:
                desc = _deny_descriptions.get(pat, pat)
                deny_examples.append(f"  - {desc}")
            denylist_block = (
                "\n\nDENIED COMMANDS (NEVER execute these, even inside the sandbox):\n"
                + "\n".join(deny_examples) + "\n"
            )
    except Exception:
        pass

    return (
        "\n\n[SANDBOX ENVIRONMENT — CODE EXECUTION ENABLED]\n"
        "You have access to a sandboxed Python environment for code execution. "
        "Use it to generate charts, run calculations, analyze data, etc.\n\n"
        "HOW TO USE:\n"
        f"- Run code via Bash: docker exec -i {container_name} python3 -c '<code>'\n"
        f"- For multi-line scripts, write to a temp file first, then:\n"
        f"    docker exec -i {container_name} python3 /tmp/script.py\n"
        f"    (Use: docker exec -i {container_name} sh -c 'cat > /tmp/script.py << \"PYEOF\"\n"
        f"    <your script>\n"
        f"    PYEOF'\n"
        f"    Then: docker exec -i {container_name} python3 /tmp/script.py)\n"
        f"- Save output files (charts, CSVs) to /workspace/output/ inside the container\n"
        f"- Available libraries: matplotlib, numpy, pandas, seaborn, plotly, scipy, "
        f"scikit-learn, sympy, pillow, beautifulsoup4, tabulate\n"
        f"- The sandbox has NO internet access\n"
        f"- Output files appear on the host at: {output_dir}\n\n"
        "WHEN TO USE:\n"
        "- User asks for a chart, graph, plot, or visualization → generate with matplotlib/plotly, save to /workspace/output/\n"
        "- User asks for data analysis or calculations → run Python code\n"
        "- User asks you to draw, create an image, or produce a visual → generate it\n"
        "- Math problems that benefit from computation → use Python\n\n"
        "IMPORTANT: Always save generated images as PNG to /workspace/output/ with descriptive filenames.\n"
        "Example: plt.savefig('/workspace/output/btc_price_chart.png', dpi=150, bbox_inches='tight')\n"
        + denylist_block
    )


# ── Legacy compatibility ──────────────────────────────────────────

def wrap_command(cmd: list[str], config: dict) -> list[str]:
    """Legacy wrapper — no longer wraps the entire claude command.

    Sandbox is now handled via docker exec inside the Claude session,
    not by wrapping the claude CLI itself.
    """
    return cmd
