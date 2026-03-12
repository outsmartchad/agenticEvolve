"""Gateway configuration — loads from config.yaml and .env."""
import os
import yaml
from pathlib import Path

EXODIR = Path.home() / ".agenticEvolve"
CONFIG_PATH = EXODIR / "config.yaml"
ENV_PATH = EXODIR / ".env"

DEFAULT_CONFIG = {
    "model": "sonnet",
    "daily_cost_cap": 5.0,
    "weekly_cost_cap": 25.0,
    "session_reset_policy": "idle",
    "session_idle_minutes": 120,
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


def load_config() -> dict:
    """Load config.yaml merged with defaults. .env loaded into environ."""
    _load_env()

    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            user_config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
            _deep_merge(config, user_config)
        except yaml.YAMLError:
            pass

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

    return config


def _deep_merge(base: dict, override: dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
