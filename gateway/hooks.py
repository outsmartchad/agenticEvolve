"""Hook dispatcher with profile-based gating and async event system.

Hooks are grouped into profiles that control which hooks fire:
  minimal  — only critical stop hooks (lowest noise, lowest overhead)
  standard — stop + observation hooks (default)
  strict   — all hooks including edit/pre-checks (highest coverage)

Profile is set via AE_HOOK_PROFILE env var (default: standard).
Individual hooks can be disabled via AE_DISABLED_HOOKS (comma-separated).

Usage (profile gating):
    from gateway.hooks import is_hook_enabled, get_active_hooks

    if is_hook_enabled("pre_tool_observe"):
        # capture tool event ...

Usage (async event system):
    from gateway.hooks import hooks

    hooks.register("before_invoke", my_fn, modifying=True)
    prompt = await hooks.fire_modifying("before_invoke", prompt)
    await hooks.fire_void("llm_output", session_id=sid, text=text, cost=cost)
"""
import asyncio
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("agenticEvolve.hooks")

EXODIR = Path.home() / ".agenticEvolve"
HOOKS_CONFIG_PATH = EXODIR / "config" / "hooks.json"

# Profile definitions — each profile is a superset of the one above it.
# Add new hook IDs here as the hook library grows.
PROFILES: dict[str, set[str]] = {
    "minimal":  {"stop"},
    "standard": {"stop", "pre_tool_observe"},
    "strict":   {"stop", "pre_tool_observe", "post_tool_observe", "pre_edit_check"},
}

_DEFAULT_PROFILE = "standard"


def _load_config() -> dict:
    """Load hooks.json config. Returns defaults if file is missing or unreadable."""
    if HOOKS_CONFIG_PATH.exists():
        try:
            return json.loads(HOOKS_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"Failed to load hooks config: {e}. Using defaults.")
    return {"default_profile": _DEFAULT_PROFILE, "disabled_hooks": []}


def _active_profile() -> str:
    """Resolve the active hook profile.

    Priority: AE_HOOK_PROFILE env var > hooks.json default_profile > 'standard'.
    Unknown profile names fall back to 'standard'.
    """
    profile = os.environ.get("AE_HOOK_PROFILE", "").strip().lower()
    if not profile:
        cfg = _load_config()
        profile = cfg.get("default_profile", _DEFAULT_PROFILE)
    if profile not in PROFILES:
        log.warning(f"Unknown hook profile '{profile}', falling back to 'standard'")
        profile = "standard"
    return profile


def _disabled_hooks() -> set[str]:
    """Return the set of explicitly disabled hook IDs.

    Reads AE_DISABLED_HOOKS env var (comma-separated) and merges with
    the disabled_hooks list from hooks.json.
    """
    disabled: set[str] = set()

    # From environment
    env_disabled = os.environ.get("AE_DISABLED_HOOKS", "")
    if env_disabled:
        disabled.update(h.strip() for h in env_disabled.split(",") if h.strip())

    # From config file
    cfg = _load_config()
    file_disabled = cfg.get("disabled_hooks", [])
    if isinstance(file_disabled, list):
        disabled.update(file_disabled)

    return disabled


def get_active_hooks() -> set[str]:
    """Return the set of currently active hook IDs.

    Applies profile selection and subtracts any explicitly disabled hooks.
    This is the canonical source of truth for which hooks should fire.
    """
    profile = _active_profile()
    active = set(PROFILES[profile])
    active -= _disabled_hooks()
    log.debug(f"Active hooks (profile={profile}): {sorted(active)}")
    return active


def is_hook_enabled(hook_id: str) -> bool:
    """Return True if a specific hook should fire given the current profile.

    Args:
        hook_id: The hook identifier to check (e.g. 'pre_tool_observe').

    Returns:
        True if the hook is in the active profile and not explicitly disabled.
    """
    return hook_id in get_active_hooks()


# ── Async event system ────────────────────────────────────────────────────────

class HookRunner:
    """Async event dispatcher for gateway lifecycle hook points.

    Two modes:
      void      — fire-and-forget, all listeners gathered concurrently.
      modifying — sequential pipeline, each listener can mutate the payload.

    All defined hook points are listed in HOOK_POINTS. Registering a name
    not in that list is allowed but logs a warning.
    """

    HOOK_POINTS = [
        "message_received",  # (platform, chat_id, text) → None
        "before_invoke",     # (session_id, prompt) → prompt
        "llm_output",        # (session_id, text, cost) → None
        "tool_call",         # (session_id, tool_name, args) → None
        "session_start",     # (session_id, platform) → None
        "session_end",       # (session_id, summary) → None
    ]

    def __init__(self) -> None:
        self._void: dict[str, list[Callable]] = {}
        self._modifying: dict[str, list[Callable]] = {}

    def register(self, name: str, fn: Callable, modifying: bool = False) -> None:
        """Register a listener for a named hook point.

        Args:
            name: Hook point name (should be one of HOOK_POINTS).
            fn: Async callable. Void hooks receive **kwargs. Modifying hooks
                receive the payload as a single positional arg and must return
                the (possibly mutated) payload.
            modifying: If True, registers as a sequential mutating hook.
        """
        if name not in self.HOOK_POINTS:
            log.warning(f"HookRunner.register: unknown hook point '{name}'")
        if modifying:
            self._modifying.setdefault(name, []).append(fn)
        else:
            self._void.setdefault(name, []).append(fn)

    async def fire_void(self, name: str, **kwargs) -> None:
        """Fire all void listeners concurrently. Exceptions are logged, not raised."""
        listeners = self._void.get(name, [])
        if not listeners:
            return
        results = await asyncio.gather(
            *(fn(**kwargs) for fn in listeners), return_exceptions=True
        )
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.warning(f"Hook '{name}' listener[{i}] raised: {r}")

    async def fire_modifying(self, name: str, payload):
        """Run all modifying listeners sequentially, threading the payload.

        Each listener receives the current payload and must return a new payload.
        If a listener raises, the exception is logged and that step is skipped.

        Returns:
            The final mutated payload.
        """
        for fn in self._modifying.get(name, []):
            try:
                payload = await fn(payload)
            except Exception as e:
                log.warning(f"Hook '{name}' modifying listener raised (skipped): {e}")
        return payload


# Module-level singleton — import and use directly.
hooks = HookRunner()
