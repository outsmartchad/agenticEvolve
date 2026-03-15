"""Tests for gateway.sandbox — Docker isolation wrapper."""
import subprocess
from unittest.mock import patch

import pytest

from gateway.sandbox import is_docker_available, wrap_command


# ── wrap_command: passthrough when sandbox disabled ──────────────

class TestSandboxDisabled:
    """wrap_command should return cmd unchanged when sandbox is off."""

    def test_no_sandbox_key(self):
        cmd = ["claude", "-p", "hello"]
        assert wrap_command(cmd, {}) == cmd

    def test_enabled_false(self):
        cmd = ["claude", "-p", "hello"]
        config = {"sandbox": {"enabled": False, "backend": "docker"}}
        assert wrap_command(cmd, config) == cmd

    def test_backend_host(self):
        cmd = ["claude", "-p", "hello"]
        config = {"sandbox": {"enabled": True, "backend": "host"}}
        assert wrap_command(cmd, config) == cmd

    def test_none_config(self):
        cmd = ["claude", "-p", "hello"]
        assert wrap_command(cmd, None) == cmd


# ── wrap_command: docker backend ─────────────────────────────────

class TestDockerBackend:
    """wrap_command should produce correct docker run args."""

    BASE_CONFIG = {
        "sandbox": {
            "enabled": True,
            "backend": "docker",
            "image": "python:3.12-slim",
            "mount_cwd": True,
            "network": True,
            "timeout": 600,
        }
    }

    def test_basic_docker_wrap(self):
        cmd = ["claude", "-p", "hello"]
        result = wrap_command(cmd, self.BASE_CONFIG)

        assert result[0] == "docker"
        assert result[1] == "run"
        assert "--rm" in result
        assert "python:3.12-slim" in result
        # Original command must appear at the end
        assert result[-3:] == ["claude", "-p", "hello"]

    def test_network_isolation(self):
        config = {
            "sandbox": {
                "enabled": True,
                "backend": "docker",
                "image": "python:3.12-slim",
                "mount_cwd": False,
                "network": False,
                "timeout": 600,
            }
        }
        result = wrap_command(["claude", "-p", "test"], config)
        assert "--network=none" in result

    def test_network_allowed(self):
        result = wrap_command(["claude", "-p", "test"], self.BASE_CONFIG)
        assert "--network=none" not in result

    def test_mount_cwd_enabled(self):
        result = wrap_command(["claude", "-p", "test"], self.BASE_CONFIG)
        assert "-v" in result
        v_idx = result.index("-v")
        assert result[v_idx + 1] == ".:/workspace"
        assert "-w" in result
        w_idx = result.index("-w")
        assert result[w_idx + 1] == "/workspace"

    def test_mount_cwd_disabled(self):
        config = {
            "sandbox": {
                "enabled": True,
                "backend": "docker",
                "image": "node:20-slim",
                "mount_cwd": False,
                "network": True,
                "timeout": 300,
            }
        }
        result = wrap_command(["claude", "-p", "test"], config)
        assert "-v" not in result
        assert "-w" not in result

    def test_custom_image(self):
        config = {
            "sandbox": {
                "enabled": True,
                "backend": "docker",
                "image": "ubuntu:22.04",
                "mount_cwd": False,
                "network": True,
                "timeout": 60,
            }
        }
        result = wrap_command(["claude", "-p", "test"], config)
        assert "ubuntu:22.04" in result

    def test_timeout_in_args(self):
        result = wrap_command(["claude", "-p", "test"], self.BASE_CONFIG)
        assert "--stop-timeout" in result
        idx = result.index("--stop-timeout")
        assert result[idx + 1] == "600"

    def test_default_image_when_missing(self):
        config = {
            "sandbox": {
                "enabled": True,
                "backend": "docker",
            }
        }
        result = wrap_command(["claude", "-p", "test"], config)
        assert "python:3.12-slim" in result


# ── is_docker_available ──────────────────────────────────────────

class TestIsDockerAvailable:
    """is_docker_available should probe for docker CLI + daemon."""

    @patch("gateway.sandbox.shutil.which", return_value=None)
    def test_no_docker_binary(self, mock_which):
        assert is_docker_available() is False

    @patch("gateway.sandbox.subprocess.run")
    @patch("gateway.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_docker_daemon_running(self, mock_which, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=0, stdout=b"", stderr=b"",
        )
        assert is_docker_available() is True

    @patch("gateway.sandbox.subprocess.run")
    @patch("gateway.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_docker_daemon_not_running(self, mock_which, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=1, stdout=b"", stderr=b"error",
        )
        assert is_docker_available() is False

    @patch("gateway.sandbox.subprocess.run", side_effect=OSError("boom"))
    @patch("gateway.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_docker_info_exception(self, mock_which, mock_run):
        assert is_docker_available() is False
