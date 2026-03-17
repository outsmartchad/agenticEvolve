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

    hooks.register("before_invoke", my_fn, modifying=True, priority=10)
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

class _HookEntry:
    """A registered hook listener with priority."""
    __slots__ = ("fn", "priority")

    def __init__(self, fn: Callable, priority: int = 0):
        self.fn = fn
        self.priority = priority


class HookRunner:
    """Async event dispatcher for gateway lifecycle hook points.

    Two modes:
      void      — fire-and-forget, all listeners gathered concurrently.
      modifying — sequential pipeline, each listener can mutate the payload.

    Priority: higher values fire first (default 0). Within same priority,
    insertion order is preserved. Inspired by OpenClaw's 25-hook typed system.

    All defined hook points are listed in HOOK_POINTS. Registering a name
    not in that list is allowed but logs a warning.
    """

    HOOK_POINTS = [
        # ── Message lifecycle ─────────────────────
        "message_received",         # void (platform, chat_id, text, user_id)
        "before_invoke",            # modifying (prompt -> prompt)
        "llm_output",               # void (session_id, text, cost)

        # ── Model selection ───────────────────────
        "before_model_resolve",     # modifying (model -> model override)

        # ── Tool execution ────────────────────────
        "before_tool_call",         # modifying (tool_name, params -> params or None to block)
        "after_tool_call",          # void (session_id, tool_name, params, result)

        # ── Session lifecycle ─────────────────────
        "session_start",            # void (session_id, platform, chat_id, user_id)
        "session_end",              # void (session_id, summary)

        # ── Gateway lifecycle ─────────────────────
        "gateway_start",            # void (adapters, config)
        "gateway_stop",             # void ()

        # ── Background tasks ──────────────────────
        "background_task_submit",   # void (task_id, session_key, description)
        "background_task_complete", # void (task_id, result)
        "background_task_failed",   # void (task_id, error)

        # ── Pipeline (evolve/absorb/decompose) ────
        "before_pipeline_stage",    # modifying (stage, prompt -> prompt)
        "after_pipeline_stage",     # void (pipeline, stage, result, cost)

        # ── Subagent orchestration ────────────────
        "subagent_spawned",         # void (task_id, model, stage)
        "subagent_ended",           # void (task_id, outcome, cost)

        # ── Message sending ───────────────────────
        "message_sending",          # modifying (text -> text)  — before platform delivery
        "message_sent",             # void (platform, chat_id, text)
    ]

    def __init__(self) -> None:
        self._void: dict[str, list[_HookEntry]] = {}
        self._modifying: dict[str, list[_HookEntry]] = {}

    def register(self, name: str, fn: Callable, modifying: bool = False,
                 priority: int = 0) -> None:
        """Register a listener for a named hook point.

        Args:
            name: Hook point name (should be one of HOOK_POINTS).
            fn: Async callable. Void hooks receive **kwargs. Modifying hooks
                receive the payload as a single positional arg and must return
                the (possibly mutated) payload.
            modifying: If True, registers as a sequential mutating hook.
            priority: Higher values fire first (default 0).
        """
        if name not in self.HOOK_POINTS:
            log.warning(f"HookRunner.register: unknown hook point '{name}'")
        entry = _HookEntry(fn, priority)
        if modifying:
            self._modifying.setdefault(name, []).append(entry)
            # Re-sort by descending priority
            self._modifying[name].sort(key=lambda e: -e.priority)
        else:
            self._void.setdefault(name, []).append(entry)
            self._void[name].sort(key=lambda e: -e.priority)

    def unregister(self, name: str, fn: Callable) -> bool:
        """Remove a listener. Returns True if found and removed."""
        for registry in (self._void, self._modifying):
            entries = registry.get(name, [])
            for i, entry in enumerate(entries):
                if entry.fn is fn:
                    entries.pop(i)
                    return True
        return False

    def has_hooks(self, name: str) -> bool:
        """O(1) check whether any listeners are registered for a hook point."""
        return bool(self._void.get(name)) or bool(self._modifying.get(name))

    async def fire_void(self, name: str, **kwargs) -> None:
        """Fire all void listeners concurrently. Exceptions are logged, not raised."""
        entries = self._void.get(name, [])
        if not entries:
            return
        results = await asyncio.gather(
            *(e.fn(**kwargs) for e in entries), return_exceptions=True
        )
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.warning(f"Hook '{name}' listener[{i}] raised: {r}")

    async def fire_modifying(self, name: str, payload, merge_fn: Callable | None = None):
        """Run all modifying listeners sequentially, threading the payload.

        Each listener receives the current payload and must return a new payload.
        If a listener raises, the exception is logged and that step is skipped.

        Args:
            name: Hook point name.
            payload: The value to thread through listeners.
            merge_fn: Optional function(old_payload, new_payload) -> merged_payload.
                      If not provided, the listener's return value replaces payload directly.

        Returns:
            The final mutated payload.
        """
        for entry in self._modifying.get(name, []):
            try:
                result = await entry.fn(payload)
                if merge_fn is not None:
                    payload = merge_fn(payload, result)
                else:
                    payload = result
            except Exception as e:
                log.warning(f"Hook '{name}' modifying listener raised (skipped): {e}")
        return payload

    def listener_count(self, name: str) -> int:
        """Return total listener count (void + modifying) for a hook point."""
        return len(self._void.get(name, [])) + len(self._modifying.get(name, []))

    def registered_hooks(self) -> dict[str, int]:
        """Return a dict of hook_name -> listener_count for all hooks with listeners."""
        result = {}
        for name in set(list(self._void.keys()) + list(self._modifying.keys())):
            count = self.listener_count(name)
            if count > 0:
                result[name] = count
        return result


# Module-level singleton — import and use directly.
hooks = HookRunner()
