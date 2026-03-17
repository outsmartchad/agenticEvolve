"""Gateway configuration — loads from config.yaml and .env.

Supports hot-reload: tracks config.yaml mtime, reloads on change.
Inspired by ZeroClaw's hot config reloading pattern.
"""
import copy
import logging
import os
import yaml
from pathlib import Path

log = logging.getLogger("agenticEvolve.config")

EXODIR = Path.home() / ".agenticEvolve"
CONFIG_PATH = EXODIR / "config.yaml"
ENV_PATH = EXODIR / ".env"

DEFAULT_CONFIG = {
    "model": "sonnet",
    "daily_cost_cap": 5.0,
    "weekly_cost_cap": 25.0,
    "session_reset_policy": "idle",
    "session_idle_minutes": 120,

    # Autonomy levels (ZeroClaw pattern)
    # "full" = --dangerously-skip-permissions (current default)
    # "supervised" = allowed_tools whitelist, agent asks before risky ops
    # "readonly" = only read tools, no writes/bash
    "autonomy": "full",
    "allowed_tools": [],    # empty = use autonomy level defaults
    "forbidden_paths": [],  # paths agent must never read/write

    # Security (ZeroClaw deny-by-default pattern)
    "security": {
        "deny_by_default": False,   # when True, empty allowed_users = deny all
        "filesystem_scoping": [],   # allowed directory prefixes (empty = allow all)
        "block_symlink_escape": True,
    },

    "platforms": {
        "telegram": {
            "enabled": False,
            "token": "",
            "allowed_users": [],
            "home_channel": "",
        },
        "discord": {
            "enabled": False,
            "token": "",
            "allowed_users": [],
            "home_channel": "",
        },
        "whatsapp": {
            "enabled": False,
            "allowed_users": [],
        },
    },
    "cron": {
        "enabled": True,
    },
}

# ── Hot-reload state ─────────────────────────────────────────────
_config_mtime: float = 0.0
_cached_config: dict | None = None


def _load_env():
    """Load .env file into os.environ (simple key=value parser)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def load_config(force: bool = False) -> dict:
    """Load config.yaml merged with defaults. .env loaded into environ.

    Hot-reload: returns cached config unless config.yaml has been modified.
    Pass force=True to bypass the cache.
    """
    global _config_mtime, _cached_config

    # Hot-reload check: skip disk read if mtime unchanged
    if not force and _cached_config is not None:
        try:
            current_mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0
            if current_mtime == _config_mtime:
                return _cached_config
            log.info(f"Config file changed (mtime {_config_mtime} -> {current_mtime}), hot-reloading")
        except OSError:
            return _cached_config

    _load_env()

    config = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            user_config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
            _deep_merge(config, user_config)
            _config_mtime = CONFIG_PATH.stat().st_mtime
        except yaml.YAMLError as e:
            log.warning(f"Failed to parse config.yaml: {e}")
            if _cached_config is not None:
                return _cached_config

    # Override from env vars
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        config["platforms"]["telegram"]["token"] = os.environ["TELEGRAM_BOT_TOKEN"]
        config["platforms"]["telegram"]["enabled"] = True
    if os.environ.get("TELEGRAM_CHAT_ID"):
        config["platforms"]["telegram"]["home_channel"] = os.environ["TELEGRAM_CHAT_ID"]
    if os.environ.get("DISCORD_BOT_TOKEN"):
        config["platforms"]["discord"]["token"] = os.environ["DISCORD_BOT_TOKEN"]
        config["platforms"]["discord"]["enabled"] = True
    if os.environ.get("DISCORD_HOME_CHANNEL"):
        config["platforms"]["discord"]["home_channel"] = os.environ["DISCORD_HOME_CHANNEL"]

    _cached_config = config
    return config


def reload_config() -> tuple[dict, list[str]]:
    """Force-reload config and return (new_config, list_of_changed_keys).

    Used by /config command and hot-reload checks.
    """
    old = copy.deepcopy(_cached_config) if _cached_config else {}
    new = load_config(force=True)
    changes = _diff_configs(old, new)
    if changes:
        log.info(f"Config reloaded — changed: {', '.join(changes)}")
    return new, changes


def config_changed() -> bool:
    """Check if config.yaml has been modified since last load. O(1) stat check."""
    try:
        current_mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0
        return current_mtime != _config_mtime
    except OSError:
        return False


def _diff_configs(old: dict, new: dict, prefix: str = "") -> list[str]:
    """Return list of changed key paths between two configs."""
    changes = []
    all_keys = set(list(old.keys()) + list(new.keys()))
    for k in all_keys:
        path = f"{prefix}.{k}" if prefix else k
        old_v = old.get(k)
        new_v = new.get(k)
        if isinstance(old_v, dict) and isinstance(new_v, dict):
            changes.extend(_diff_configs(old_v, new_v, path))
        elif old_v != new_v:
            changes.append(path)
    return changes


def validate_config(config: dict) -> list[str]:
    """Validate config semantics. Returns list of error messages (empty = valid)."""
    errors = []

    # Cost caps must be non-negative
    for key in ("daily_cost_cap", "weekly_cost_cap"):
        val = config.get(key)
        if val is not None and (not isinstance(val, (int, float)) or val < 0):
            errors.append(f"{key} must be a non-negative number")

    # Model must be a known string
    model = config.get("model")
    if model and not isinstance(model, str):
        errors.append("model must be a string")

    # Exec mode validation
    exec_cfg = config.get("exec", {})
    if exec_cfg:
        if exec_cfg.get("security") and exec_cfg["security"] not in ("deny", "allowlist", "full"):
            errors.append("exec.security must be deny|allowlist|full")
        if exec_cfg.get("ask") and exec_cfg["ask"] not in ("off", "on-miss", "always"):
            errors.append("exec.ask must be off|on-miss|always")
        if exec_cfg.get("mode") and exec_cfg["mode"] not in ("sandbox", "gateway"):
            errors.append("exec.mode must be sandbox|gateway")

    # Platform configs
    platforms = config.get("platforms", {})
    for name, pcfg in platforms.items():
        if not isinstance(pcfg, dict):
            errors.append(f"platforms.{name} must be a dict")
            continue
        users = pcfg.get("allowed_users", [])
        if users and not isinstance(users, list):
            errors.append(f"platforms.{name}.allowed_users must be a list")

    # Rate limiting
    rl = config.get("rate_limit", {})
    if rl:
        for key in ("per_user_per_minute", "per_user_per_hour"):
            val = rl.get(key)
            if val is not None and (not isinstance(val, int) or val < 0):
                errors.append(f"rate_limit.{key} must be a non-negative integer")

    return errors


def _deep_merge(base: dict, override: dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
