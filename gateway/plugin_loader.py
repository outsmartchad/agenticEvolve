"""Plugin discovery and loading for agenticEvolve.

Plugins live in ~/.agenticEvolve/plugins/ as Python modules.
Each plugin must expose a `register(hooks, config)` function:

    # ~/.agenticEvolve/plugins/my_plugin.py
    def register(hooks, config):
        async def on_message(**kwargs):
            print(f"Message from {kwargs['platform']}: {kwargs['text']}")
        hooks.register("message_received", on_message, priority=5)

Plugin loading order:
  1. Files sorted alphabetically (use numeric prefixes for ordering: 00_core.py, 10_logging.py)
  2. Directories with __init__.py are loaded as packages

Plugins are loaded once at gateway startup. Config is the full gateway config dict.
"""
import importlib.util
import logging
import sys
from pathlib import Path

from .hooks import HookRunner

log = logging.getLogger("agenticEvolve.plugins")

PLUGINS_DIR = Path.home() / ".agenticEvolve" / "plugins"


class PluginInfo:
    """Metadata for a loaded plugin."""
    __slots__ = ("name", "path", "module", "loaded")

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.module = None
        self.loaded = False


def discover_plugins() -> list[PluginInfo]:
    """Find all plugin modules in PLUGINS_DIR.

    Returns a sorted list of PluginInfo objects.
    """
    if not PLUGINS_DIR.exists():
        return []

    plugins = []

    # Single .py files
    for f in sorted(PLUGINS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        name = f.stem
        plugins.append(PluginInfo(name, f))

    # Directories with __init__.py
    for d in sorted(PLUGINS_DIR.iterdir()):
        if d.is_dir() and (d / "__init__.py").exists():
            if d.name.startswith("_"):
                continue
            plugins.append(PluginInfo(d.name, d / "__init__.py"))

    return plugins


def load_plugin(info: PluginInfo) -> bool:
    """Load a single plugin module. Returns True on success."""
    try:
        spec = importlib.util.spec_from_file_location(
            f"agenticEvolve_plugin_{info.name}", str(info.path))
        if spec is None or spec.loader is None:
            log.warning(f"Plugin '{info.name}': could not create module spec")
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"agenticEvolve_plugin_{info.name}"] = module
        spec.loader.exec_module(module)

        info.module = module
        info.loaded = True
        return True
    except Exception as e:
        log.error(f"Plugin '{info.name}' failed to load: {e}")
        return False


def register_plugin(info: PluginInfo, hook_runner: HookRunner, config: dict) -> bool:
    """Call the plugin's register() function. Returns True on success."""
    if not info.loaded or info.module is None:
        return False

    register_fn = getattr(info.module, "register", None)
    if register_fn is None:
        log.warning(f"Plugin '{info.name}' has no register() function — skipped")
        return False

    try:
        register_fn(hook_runner, config)
        log.info(f"Plugin '{info.name}' registered successfully")
        return True
    except Exception as e:
        log.error(f"Plugin '{info.name}' register() failed: {e}")
        return False


def load_all_plugins(hook_runner: HookRunner, config: dict) -> list[PluginInfo]:
    """Discover, load, and register all plugins.

    Returns the list of successfully loaded plugins.
    """
    plugins = discover_plugins()
    if not plugins:
        log.debug("No plugins found")
        return []

    log.info(f"Discovered {len(plugins)} plugin(s): {[p.name for p in plugins]}")

    loaded = []
    for info in plugins:
        if load_plugin(info) and register_plugin(info, hook_runner, config):
            loaded.append(info)

    if loaded:
        # Log hook stats after all plugins loaded
        registered = hook_runner.registered_hooks()
        log.info(f"Plugins loaded: {len(loaded)}/{len(plugins)} — "
                 f"hooks wired: {sum(registered.values())} across {len(registered)} points")

    return loaded
