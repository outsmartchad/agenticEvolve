"""Tests for the plugin loader (Phase 3)."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gateway.plugin_loader import (
    PluginInfo, discover_plugins, load_plugin,
    register_plugin, load_all_plugins, PLUGINS_DIR
)
from gateway.hooks import HookRunner


class TestPluginInfo:
    def test_defaults(self):
        info = PluginInfo("test", Path("/tmp/test.py"))
        assert info.name == "test"
        assert info.module is None
        assert not info.loaded


class TestDiscoverPlugins:
    def test_no_dir(self, tmp_path):
        with patch("gateway.plugin_loader.PLUGINS_DIR", tmp_path / "nonexistent"):
            plugins = discover_plugins()
            assert plugins == []

    def test_finds_py_files(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "alpha.py").write_text("def register(h, c): pass")
        (plugins_dir / "beta.py").write_text("def register(h, c): pass")
        (plugins_dir / "_hidden.py").write_text("")  # Should be skipped
        (plugins_dir / "not_py.txt").write_text("")  # Should be skipped

        with patch("gateway.plugin_loader.PLUGINS_DIR", plugins_dir):
            plugins = discover_plugins()
            names = [p.name for p in plugins]
            assert "alpha" in names
            assert "beta" in names
            assert "_hidden" not in names
            assert len(plugins) == 2

    def test_finds_packages(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        pkg = plugins_dir / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("def register(h, c): pass")

        with patch("gateway.plugin_loader.PLUGINS_DIR", plugins_dir):
            plugins = discover_plugins()
            assert len(plugins) == 1
            assert plugins[0].name == "mypkg"

    def test_sorted_alphabetically(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "10_second.py").write_text("")
        (plugins_dir / "00_first.py").write_text("")
        (plugins_dir / "20_third.py").write_text("")

        with patch("gateway.plugin_loader.PLUGINS_DIR", plugins_dir):
            plugins = discover_plugins()
            names = [p.name for p in plugins]
            assert names == ["00_first", "10_second", "20_third"]


class TestLoadPlugin:
    def test_load_valid_module(self, tmp_path):
        plugin_file = tmp_path / "good.py"
        plugin_file.write_text("VALUE = 42\ndef register(h, c): pass")
        info = PluginInfo("good", plugin_file)
        assert load_plugin(info)
        assert info.loaded
        assert info.module is not None
        assert info.module.VALUE == 42

    def test_load_bad_syntax(self, tmp_path):
        plugin_file = tmp_path / "bad.py"
        plugin_file.write_text("def broken(:\n  pass")
        info = PluginInfo("bad", plugin_file)
        assert not load_plugin(info)
        assert not info.loaded


class TestRegisterPlugin:
    def test_register_calls_fn(self, tmp_path):
        plugin_file = tmp_path / "test_reg.py"
        plugin_file.write_text(
            "def register(hooks, config):\n"
            "    hooks.marker = 'called'\n")
        info = PluginInfo("test_reg", plugin_file)
        load_plugin(info)

        runner = HookRunner()
        assert register_plugin(info, runner, {"key": "val"})
        assert hasattr(runner, "marker")
        assert runner.marker == "called"

    def test_register_no_fn(self, tmp_path):
        plugin_file = tmp_path / "nofn.py"
        plugin_file.write_text("VALUE = 1")
        info = PluginInfo("nofn", plugin_file)
        load_plugin(info)
        runner = HookRunner()
        assert not register_plugin(info, runner, {})

    def test_register_exception(self, tmp_path):
        plugin_file = tmp_path / "errfn.py"
        plugin_file.write_text(
            "def register(hooks, config):\n"
            "    raise RuntimeError('boom')\n")
        info = PluginInfo("errfn", plugin_file)
        load_plugin(info)
        runner = HookRunner()
        assert not register_plugin(info, runner, {})


class TestLoadAllPlugins:
    def test_end_to_end(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "good.py").write_text(
            "async def on_msg(**kw): pass\n"
            "def register(hooks, config):\n"
            "    hooks.register('message_received', on_msg)\n")
        (plugins_dir / "bad.py").write_text("def register(h, c): raise Exception('no')")

        runner = HookRunner()
        with patch("gateway.plugin_loader.PLUGINS_DIR", plugins_dir):
            loaded = load_all_plugins(runner, {"key": "val"})
            assert len(loaded) == 1
            assert loaded[0].name == "good"
            assert runner.has_hooks("message_received")
