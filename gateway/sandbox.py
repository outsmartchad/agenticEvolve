"""Docker sandbox wrapper for claude -p execution."""
import logging
import shutil
import subprocess

log = logging.getLogger("agenticEvolve.sandbox")


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


def wrap_command(cmd: list[str], config: dict) -> list[str]:
    """Optionally wrap *cmd* in ``docker run`` based on sandbox config.

    Args:
        cmd: The original command list (e.g. ``["claude", "-p", ...]``).
        config: Full gateway config dict.  Reads the ``sandbox`` section.

    Returns:
        The command unchanged when sandboxing is disabled, or a new list
        prefixed with ``docker run --rm ...`` when Docker backend is active.
    """
    sandbox = config.get("sandbox", {}) if config else {}

    if not sandbox.get("enabled", False):
        return cmd

    backend = sandbox.get("backend", "host")
    if backend != "docker":
        return cmd

    image = sandbox.get("image", "python:3.12-slim")
    mount_cwd = sandbox.get("mount_cwd", True)
    network = sandbox.get("network", True)
    timeout = sandbox.get("timeout", 600)

    docker_cmd: list[str] = ["docker", "run", "--rm"]

    if not network:
        docker_cmd.append("--network=none")

    if mount_cwd:
        docker_cmd.extend(["-v", ".:/workspace", "-w", "/workspace"])

    if timeout:
        docker_cmd.extend(["--stop-timeout", str(timeout)])

    docker_cmd.append(image)
    docker_cmd.extend(cmd)

    log.debug("Sandbox wrapping: %s", docker_cmd)
    return docker_cmd
