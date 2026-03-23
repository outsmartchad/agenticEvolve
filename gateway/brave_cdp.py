"""Persistent Brave browser manager for login-required sites.

Launches Brave with --remote-debugging-port so the browser survives
across multiple claude -p calls. Agent connects via Playwright CDP.
"""
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("agenticEvolve.brave_cdp")


class BraveCDPManager:
    """Manage a persistent Brave browser instance with CDP for multi-turn sessions."""

    def __init__(self, config: dict):
        self.path = config.get(
            "path",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        )
        self.port = config.get("debug_port", 9222)
        self.profile_dir = Path(
            config.get("profile_dir", "~/.agenticEvolve/browser-profiles/brave")
        ).expanduser()
        self._process: subprocess.Popen | None = None

    def ensure_running(self) -> int:
        """Start Brave with CDP if not already running. Returns the debug port."""
        if self._process and self._process.poll() is None:
            return self.port
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Launching Brave CDP on port {self.port}")
        self._process = subprocess.Popen(
            [
                self.path,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return self.port

    def is_running(self) -> bool:
        """Check if the managed Brave process is still alive."""
        return self._process is not None and self._process.poll() is None

    def stop(self):
        """Terminate the managed Brave process."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            log.info("Brave CDP stopped")
