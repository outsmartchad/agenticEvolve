"""Load channel-specific knowledge prompts from JSON config.

Reads from ~/.agenticEvolve/channel_knowledge.json with mtime-based
cache invalidation. Falls back to an empty dict if the file is missing.
"""
import json
import logging
from pathlib import Path

log = logging.getLogger("agenticEvolve.channel_knowledge")

_CONFIG_PATH = Path.home() / ".agenticEvolve" / "channel_knowledge.json"

_cache: dict[str, str] = {}
_cache_mtime: float = 0.0


def load_channel_knowledge() -> dict[str, str]:
    """Return channel_id -> knowledge prompt mapping.

    Caches the result and only re-reads when the file's mtime changes.
    Returns an empty dict if the file doesn't exist or is invalid.
    """
    global _cache, _cache_mtime

    if not _CONFIG_PATH.exists():
        return _cache if _cache_mtime > 0 else {}

    try:
        mtime = _CONFIG_PATH.stat().st_mtime
        if mtime == _cache_mtime and _cache:
            return _cache

        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            log.warning("channel_knowledge.json: expected dict, got %s", type(data).__name__)
            return _cache

        _cache = data
        _cache_mtime = mtime
        log.debug("Loaded %d channel knowledge entries", len(_cache))
        return _cache

    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to read channel_knowledge.json: %s", e)
        return _cache
