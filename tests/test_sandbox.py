"""Tests for gateway.sandbox — Docker sandbox for code execution."""
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from gateway.sandbox import (
    is_docker_available,
    is_image_built,
    wrap_command,
    _container_name,
    _get_output_dir,
    get_output_images,
    clear_output,
    build_sandbox_prompt,
    CONTAINER_PREFIX,
    SANDBOX_IMAGE,
    SHARED_OUTPUT_DIR,
)


# ── wrap_command: legacy passthrough ─────────────────────────────

class TestWrapCommand:
    """wrap_command always passes through now (legacy compat)."""

    def test_passthrough(self):
        cmd = ["claude", "-p", "hello"]
        assert wrap_command(cmd, {}) == cmd

    def test_passthrough_with_sandbox_enabled(self):
        cmd = ["claude", "-p", "hello"]
        config = {"sandbox": {"enabled": True}}
        assert wrap_command(cmd, config) == cmd

    def test_none_config(self):
        cmd = ["claude", "-p", "hello"]
        assert wrap_command(cmd, None) == cmd


# ── Container naming ─────────────────────────────────────────────

class TestContainerNaming:
    """Container names should be deterministic and prefixed."""

    def test_deterministic(self):
        name1 = _container_name("whatsapp:123@g.us")
        name2 = _container_name("whatsapp:123@g.us")
        assert name1 == name2

    def test_different_sessions(self):
        name1 = _container_name("whatsapp:123@g.us")
        name2 = _container_name("whatsapp:456@g.us")
        assert name1 != name2

    def test_prefixed(self):
        name = _container_name("test-session")
        assert name.startswith(CONTAINER_PREFIX)

    def test_reasonable_length(self):
        name = _container_name("some-long-session-key-with-many-characters")
        assert len(name) < 50


# ── Output directory ─────────────────────────────────────────────

class TestOutputDir:
    """Output directory should be deterministic and under SHARED_OUTPUT_DIR."""

    def test_under_shared_dir(self):
        d = _get_output_dir("test-session")
        assert str(d).startswith(str(SHARED_OUTPUT_DIR))

    def test_deterministic(self):
        d1 = _get_output_dir("test-session")
        d2 = _get_output_dir("test-session")
        assert d1 == d2


# ── Image extraction ─────────────────────────────────────────────

class TestGetOutputImages:
    """get_output_images should find image files in the output dir."""

    def test_no_images(self, tmp_path):
        with patch("gateway.sandbox._get_output_dir", return_value=tmp_path):
            assert get_output_images("test") == []

    def test_finds_png(self, tmp_path):
        (tmp_path / "chart.png").write_bytes(b"fake-png")
        (tmp_path / "data.csv").write_text("a,b\n1,2")
        with patch("gateway.sandbox._get_output_dir", return_value=tmp_path):
            images = get_output_images("test")
            assert len(images) == 1
            assert images[0].name == "chart.png"

    def test_finds_multiple_formats(self, tmp_path):
        for ext in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"]:
            (tmp_path / f"img{ext}").write_bytes(b"fake")
        with patch("gateway.sandbox._get_output_dir", return_value=tmp_path):
            images = get_output_images("test")
            assert len(images) == 6


# ── Clear output ─────────────────────────────────────────────────

class TestClearOutput:
    """clear_output should remove all files from the output dir."""

    def test_clears_files(self, tmp_path):
        (tmp_path / "chart.png").write_bytes(b"fake")
        (tmp_path / "data.csv").write_text("a,b")
        with patch("gateway.sandbox._get_output_dir", return_value=tmp_path):
            clear_output("test")
            assert list(tmp_path.iterdir()) == []


# ── Sandbox prompt ───────────────────────────────────────────────

class TestSandboxPrompt:
    """build_sandbox_prompt should produce useful instructions."""

    def test_contains_container_name(self):
        prompt = build_sandbox_prompt("ae-sandbox-abc123", "/tmp/out")
        assert "ae-sandbox-abc123" in prompt

    def test_contains_output_dir(self):
        prompt = build_sandbox_prompt("ae-sandbox-abc123", "/tmp/out")
        assert "/tmp/out" in prompt

    def test_mentions_matplotlib(self):
        prompt = build_sandbox_prompt("test", "/tmp/out")
        assert "matplotlib" in prompt

    def test_mentions_savefig(self):
        prompt = build_sandbox_prompt("test", "/tmp/out")
        assert "savefig" in prompt


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


# ── is_image_built ───────────────────────────────────────────────

class TestIsImageBuilt:
    """is_image_built should check for the sandbox Docker image."""

    @patch("gateway.sandbox.subprocess.run")
    def test_image_exists(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b"",
        )
        assert is_image_built() is True

    @patch("gateway.sandbox.subprocess.run")
    def test_image_missing(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=b"",
        )
        assert is_image_built() is False
