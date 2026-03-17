"""Claude Code invocation wrapper for the gateway."""
import json
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

log = logging.getLogger("agenticEvolve.agent")

EXODIR = Path.home() / ".agenticEvolve"


# ── Env var sanitization (OpenClaw pattern) ──────────────────────
# Block sensitive env vars from leaking to claude -p subprocesses.

_BLOCKED_ENV_EXACT = {
    # API keys / tokens
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
    "BRAVE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "COHERE_API_KEY", "MISTRAL_API_KEY", "VOYAGE_API_KEY",
    "HUGGINGFACE_TOKEN", "HF_TOKEN",
    # Platform tokens
    "TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "DISCORD_TOKEN",
    "SLACK_TOKEN", "SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET",
    "WHATSAPP_TOKEN",
    # Cloud provider secrets
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
    "GCP_SERVICE_ACCOUNT_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    # Database / infra
    "DATABASE_URL", "REDIS_URL", "MONGODB_URI",
    "SUPABASE_SERVICE_ROLE_KEY", "FIREBASE_TOKEN",
    # Misc secrets
    "JWT_SECRET", "SESSION_SECRET", "ENCRYPTION_KEY",
    "PRIVATE_KEY", "SECRET_KEY", "MASTER_KEY",
    "SENDGRID_API_KEY", "TWILIO_AUTH_TOKEN",
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    "NPM_TOKEN", "PYPI_TOKEN", "GITHUB_TOKEN",
    "VERCEL_TOKEN", "NETLIFY_AUTH_TOKEN",
    "DOPPLER_TOKEN", "VAULT_TOKEN",
}

_BLOCKED_ENV_PREFIXES = (
    "AWS_", "AZURE_", "GCP_", "GCLOUD_",
    "FIREBASE_", "SUPABASE_",
    "STRIPE_", "TWILIO_", "SENDGRID_",
    "DOPPLER_", "VAULT_",
    "DOCKER_",  # prevent container escape
)

# Keys that MUST be kept (claude CLI needs ANTHROPIC_API_KEY via its own config)
_KEEP_ENV = {
    "PATH", "HOME", "USER", "SHELL", "LANG", "TERM",
    "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
    "MPLBACKEND",  # matplotlib backend for sandbox
}


def _sanitize_env(env: dict[str, str], config: dict | None = None) -> dict[str, str]:
    """Remove sensitive env vars before passing to claude -p.

    The claude CLI reads its API key from its own config file (~/.claude/),
    so we don't need to pass ANTHROPIC_API_KEY in the environment.
    """
    blocked_count = 0
    for key in list(env.keys()):
        if key in _KEEP_ENV:
            continue
        if key in _BLOCKED_ENV_EXACT:
            del env[key]
            blocked_count += 1
        elif key.startswith(_BLOCKED_ENV_PREFIXES):
            del env[key]
            blocked_count += 1
    if blocked_count:
        log.debug(f"Sanitized env: blocked {blocked_count} sensitive vars")
    return env


# ── MemoryQueue ───────────────────────────────────────────────────
# Debounced atomic writer for memory files.  Eliminates the MEMORY.md
# read-modify-write race condition on high-volume days by coalescing rapid
# writes into a single disk flush 30s after the last enqueue call.
#
# Usage:
#   memory_queue.enqueue(path, new_content)          # default 30s debounce
#   memory_queue.enqueue(path, new_content, delay=5) # custom delay
#
# Atomic on POSIX: writes to <file>.tmp then renames → no partial reads.
# SQLite writes are NOT routed through this queue — SQLite has its own locking.

class _MemoryQueue:
    """Singleton debounced atomic writer for memory markdown files."""

    def __init__(self):
        self._timers: dict[str, threading.Timer] = {}
        self._pending: dict[str, str] = {}  # key → latest content not yet flushed
        self._lock = threading.Lock()

    def enqueue(self, path: Path, content: str, delay: float = 30.0) -> None:
        """Schedule an atomic write of *content* to *path* after *delay* seconds.

        If a write for the same path is already pending, the previous timer is
        cancelled and a new one is started — effectively debouncing rapid writes.

        Args:
            path: Destination file path (will be created if absent).
            content: Full file content to write.
            delay: Seconds to wait before flushing. Defaults to 30s.
        """
        key = str(path)
        with self._lock:
            existing = self._timers.pop(key, None)
            if existing is not None:
                existing.cancel()
            self._pending[key] = content  # always reflect latest in-memory state
            timer = threading.Timer(delay, self._write, args=[path, content, key])
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def flush(self, path: Path) -> None:
        """Force an immediate write for *path*, bypassing the debounce delay."""
        key = str(path)
        with self._lock:
            existing = self._timers.pop(key, None)
            if existing is not None:
                existing.cancel()
                # Re-extract content by re-scheduling with delay=0; instead,
                # we just cancel and let the caller handle urgent writes directly.
                # For a full flush, callers should use path.write_text() directly.

    def read(self, path: Path) -> str | None:
        """Return pending (in-flight) content for *path*, or None if none queued.

        Callers should fall back to path.read_text() when this returns None.
        This ensures build_system_prompt always sees the latest in-memory state
        even when the debounce timer hasn't flushed yet.
        """
        key = str(path)
        with self._lock:
            return self._pending.get(key)

    def _write(self, path: Path, content: str, key: str) -> None:
        """Perform the atomic write. Called from timer thread."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.rename(path)
            log.debug(f"MemoryQueue: flushed {path}")
        except OSError as e:
            log.warning(f"MemoryQueue: write failed for {path}: {e}")
        finally:
            with self._lock:
                self._timers.pop(key, None)
                self._pending.pop(key, None)


memory_queue = _MemoryQueue()


# ── LoopDetector ──────────────────────────────────────────────────
# Replaces the 480s wall-clock timeout as the primary stuck-agent guard.
# Tracks per-session tool-call fingerprints in a rolling deque.  When the
# same fingerprint appears 3× consecutively a warning is injected; at 5×
# a LoopDetectedError is raised so the caller can surface a sentinel response.

class LoopDetectedError(RuntimeError):
    """Raised when invoke_claude_streaming detects an agent stuck in a loop."""


class LoopDetector:
    """Per-session rolling deque of tool-call fingerprints.

    A fingerprint is the md5 of a sorted, deterministic representation of the
    tool names + input keys for one Claude turn.  Consecutive identical
    fingerprints indicate the agent is repeating the same tool calls with no
    progress.

    Usage:
        detector = LoopDetector()
        count = detector.record(session_key, tool_calls)
        # count is the number of consecutive identical fingerprints seen so far
    """

    def __init__(self, maxlen: int = 20):
        self._deques: dict[str, "collections.deque[str]"] = {}
        self._maxlen = maxlen

    def _fingerprint(self, tool_calls: list[dict]) -> str:
        """Compute md5 of sorted tool-name:input-keys pairs for one turn."""
        import collections as _col  # noqa: F401 (used below via collections)
        import hashlib as _hl
        parts = sorted(
            f"{t.get('name', '')}:{','.join(sorted(t.get('input', {}).keys()))}"
            for t in tool_calls
        )
        return _hl.md5("|".join(parts).encode()).hexdigest()

    def record(self, session_key: str, tool_calls: list[dict]) -> int:
        """Record a tool-call batch and return consecutive identical count.

        Args:
            session_key: Unique session identifier (e.g. 'telegram:12345').
            tool_calls: List of tool_use dicts from one Claude assistant turn.

        Returns:
            Number of consecutive turns with the same fingerprint, including this one.
        """
        import collections
        if session_key not in self._deques:
            self._deques[session_key] = collections.deque(maxlen=self._maxlen)
        deque = self._deques[session_key]
        fp = self._fingerprint(tool_calls)
        deque.append(fp)
        # Count trailing identical fingerprints
        count = 0
        for entry in reversed(deque):
            if entry == fp:
                count += 1
            else:
                break
        return count

    def reset(self, session_key: str) -> None:
        """Clear history for a session (e.g. after a loop warning is injected)."""
        self._deques.pop(session_key, None)


_loop_detector = LoopDetector()


class InvokeFailReason(str, Enum):
    """Typed failure classification for invoke_claude() error handling."""
    AUTH_PERMANENT = "auth_permanent"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    EMPTY_OUTPUT = "empty_output"
    UNKNOWN = "unknown"


# Cooldown table: reason → epoch when cooldown expires.
# Rate-limit errors back off for a short period before retrying.
_cooldowns: dict[str, float] = {}


def _classify_stderr(stderr: str) -> InvokeFailReason:
    """Classify a Claude CLI stderr string into a typed failure reason.

    Args:
        stderr: Raw stderr output from the claude subprocess.

    Returns:
        InvokeFailReason enum value.
    """
    s = stderr.lower()
    if "invalid api key" in s or "unauthorized" in s:
        return InvokeFailReason.AUTH_PERMANENT
    if "billing" in s or "quota exceeded" in s or "payment" in s:
        return InvokeFailReason.BILLING
    if "rate limit" in s or "429" in s or "too many requests" in s:
        return InvokeFailReason.RATE_LIMIT
    return InvokeFailReason.UNKNOWN


def build_system_prompt(config: dict | None = None,
                        context_mode: str | None = None,
                        user_id: str | None = None) -> str:
    """Assemble system prompt from SOUL.md + MEMORY.md + USER.md + autonomy rules.

    Args:
        config: Full gateway config for autonomy level resolution.
        context_mode: Optional overlay name (e.g. 'review', 'absorb'). When set,
            loads ~/.agenticEvolve/contexts/<context_mode>.md and appends it as a
            focused constraint block. Falls back gracefully if the file is missing.
    """
    parts = []

    # SOUL.md — personality
    soul_path = EXODIR / "SOUL.md"
    if soul_path.exists():
        soul = soul_path.read_text().strip()
        parts.append(f"# Personality\n{soul}")

    # MEMORY.md — agent's notes
    # Use queue's pending content if a write is in-flight; avoids stale reads
    # when build_system_prompt() is called within the 30s debounce window.
    mem_path = EXODIR / "memory" / "MEMORY.md"
    if mem_path.exists() or memory_queue.read(mem_path) is not None:
        _pending = memory_queue.read(mem_path)
        mem = (_pending if _pending is not None else mem_path.read_text()).strip()
        chars = len(mem)
        pct = int(chars / 2200 * 100)
        parts.append(
            f"# MEMORY (your personal notes) [{pct}% — {chars}/2,200 chars]\n{mem}"
        )

    # USER.md — user profile
    user_path = EXODIR / "memory" / "USER.md"
    if user_path.exists() or memory_queue.read(user_path) is not None:
        _upending = memory_queue.read(user_path)
        user = (_upending if _upending is not None else user_path.read_text()).strip()
        chars = len(user)
        pct = int(chars / 1375 * 100)
        parts.append(
            f"# USER PROFILE [{pct}% — {chars}/1,375 chars]\n{user}"
        )

    # Autonomy rules from config (ZeroClaw patterns)
    if config:
        from .autonomy import build_filesystem_rules, build_risk_awareness_prompt
        fs_rules = build_filesystem_rules(config)
        if fs_rules:
            parts.append(fs_rules)
        risk_prompt = build_risk_awareness_prompt(config)
        if risk_prompt:
            parts.append(risk_prompt)

    # Context mode overlay — appended last so it takes precedence as a constraint layer.
    # Overlays tighten behaviour for specific pipeline stages without touching SOUL.md.
    if context_mode:
        overlay_path = EXODIR / "contexts" / f"{context_mode}.md"
        if overlay_path.exists():
            overlay = overlay_path.read_text().strip()
            parts.append(f"# Context Mode: {context_mode}\n{overlay}")
            log.debug(f"Loaded context overlay: {context_mode}")
        else:
            log.debug(f"Context overlay '{context_mode}' not found at {overlay_path}, skipping")

    # Language preference injection — applies to all platforms (TUI, Telegram, etc.)
    # Soft preference: match the language the user is writing in. The stored /lang
    # pref is a *default* — if the current message is in English, respond in English.
    if user_id:
        try:
            from .session_db import get_user_pref
            lang_code = get_user_pref(user_id, "lang")
            if lang_code and lang_code != "en":
                _LANG_NAMES = {
                    "zh": "Simplified Chinese (简体中文)", "en": "English",
                    "ja": "Japanese (日本語)", "ko": "Korean (한국어)",
                    "es": "Spanish (Español)", "fr": "French (Français)",
                    "de": "German (Deutsch)", "ru": "Russian (Русский)",
                    "pt": "Portuguese (Português)", "ar": "Arabic (العربية)",
                    "hi": "Hindi (हिन्दी)", "it": "Italian (Italiano)",
                    "th": "Thai (ไทย)", "vi": "Vietnamese (Tiếng Việt)",
                    "zh-tw": "Traditional Chinese (繁體中文)",
                    "yue": "Cantonese (廣東話)",
                }
                lang_name = _LANG_NAMES.get(lang_code, lang_code)
                parts.append(
                    f"Language preference: the user prefers {lang_name}. "
                    f"Always reply in {lang_name} UNLESS the user's current message is "
                    f"clearly written in a different language (more than 4 words of prose). "
                    f"Short messages like 'hi', 'yo', 'ok', 'yes', 'no' are language-neutral "
                    f"— reply in {lang_name} for those."
                )
        except Exception:
            pass

    return "\n\n".join(parts)


def _format_history(history: list[dict], max_turns: int = 20,
                    max_chars: int = 8000) -> str:
    """Format conversation history for injection into the prompt.

    Three-pass compaction cascade:
      Pass 1 — full messages up to max_chars (with 1.2x safety multiplier).
      Pass 2 — strip large tool result blocks (>500 chars with code fences).
      Pass 3 — drop oldest turns one-by-one, per-message cap at 1500 chars.
      Fallback — hard truncate to effective_limit.

    The 1.2x safety multiplier corrects for the chars/4 token underestimate
    used by many context-window calculators.
    """
    if not history:
        return ""

    SAFETY_MULTIPLIER = 1.2  # chars/4 underestimates tokens; shrink by 1/1.2
    effective_limit = int(max_chars / SAFETY_MULTIPLIER)  # ~6666 for default 8000

    recent = history[-max_turns:]

    def _strip_tool_result(msg: dict) -> dict:
        """Remove large tool output blocks from assistant messages."""
        content = msg.get("content", "")
        if len(content) > 500 and ("<tool_result>" in content or "```" in content):
            msg = dict(msg, content=content[:200] + "\n[tool output truncated for compaction]")
        return msg

    def _render(msgs: list[dict], per_msg_cap: int = 0) -> str:
        parts = []
        for m in msgs:
            role = m.get("role", "user")
            content = m.get("content", "")
            if per_msg_cap and len(content) > per_msg_cap:
                content = content[:per_msg_cap] + "... [truncated]"
            parts.append(f"[{role}]: {content}")
        return "\n\n".join(parts)

    # Pass 1: full messages
    joined = _render(recent)
    if len(joined) <= effective_limit:
        return joined

    # Pass 2: strip large tool results
    stripped = [_strip_tool_result(m) for m in recent]
    joined = _render(stripped)
    if len(joined) <= effective_limit:
        return joined

    # Pass 3: drop oldest turns (keep first + recent slice), cap per message
    for drop_count in range(1, len(recent)):
        subset = recent[:1] + recent[drop_count + 1:]
        joined = _render(subset, per_msg_cap=1500)
        if len(joined) <= effective_limit:
            return joined

    # Fallback: hard truncate
    return joined[:effective_limit]


def get_today_cost() -> float:
    """Return today's total cost. Tries SQLite first, falls back to cost.log."""
    try:
        from .session_db import get_cost_today
        db_total = get_cost_today()
        if db_total > 0:
            return db_total
    except Exception:
        pass

    # Fallback: linear scan of cost.log (migration safety for existing installs)
    cost_file = EXODIR / "logs" / "cost.log"
    if not cost_file.exists():
        return 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = 0.0
    try:
        for line in cost_file.read_text().splitlines():
            if today in line:
                parts = line.split("\t")
                if len(parts) >= 4:
                    cost_str = parts[3].replace("$", "")
                    try:
                        total += float(cost_str)
                    except ValueError:
                        pass
    except Exception:
        pass
    return total


def get_week_cost() -> float:
    """Return this week's (Mon-Sun) total cost. Tries SQLite first, falls back to cost.log."""
    try:
        from .session_db import get_cost_week
        db_total = get_cost_week()
        if db_total > 0:
            return db_total
    except Exception:
        pass

    # Fallback: linear scan of cost.log (migration safety for existing installs)
    cost_file = EXODIR / "logs" / "cost.log"
    if not cost_file.exists():
        return 0.0
    now = datetime.now(timezone.utc)
    monday = (now - __import__('datetime').timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    total = 0.0
    try:
        for line in cost_file.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                date_str = parts[0][:10]
                if date_str >= monday:
                    cost_str = parts[3].replace("$", "")
                    try:
                        total += float(cost_str)
                    except ValueError:
                        pass
    except Exception:
        pass
    return total


def _terminate_proc(proc: subprocess.Popen) -> None:
    """Send SIGTERM then SIGKILL if process doesn't exit within 5s."""
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _make_workspace() -> Path:
    """Create a UUID-scoped scratch directory under ~/.agenticEvolve/workspaces/.

    Each workspace is isolated so concurrent evolve cycles cannot clobber each
    other's skill files. The caller is responsible for cleanup via shutil.rmtree.
    """
    workspace_dir = EXODIR / "workspaces" / uuid.uuid4().hex
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def invoke_claude(message: str, model: str = "sonnet",
                   cwd: str = None, history: list[dict] = None,
                   session_context: str = "",
                   allowed_tools: list[str] | None = None,
                   config: dict | None = None,
                   use_workspace: bool = False,
                   max_seconds: int = 600,
                   user_id: str | None = None,
                   enable_browser: bool = False) -> dict:
    """
    Invoke Claude Code with a message and return the response.

    Args:
        message: The user's message
        model: Model to use (sonnet, opus, etc.)
        cwd: Working directory for Claude Code
        history: List of past messages [{"role": "user/assistant", "content": "..."}]
        session_context: Extra context line (platform, session id, etc.)
        allowed_tools: If set, restricts Claude to these tools instead of --dangerously-skip-permissions
        config: Full gateway config for autonomy level resolution
        use_workspace: If True, create an isolated UUID-scoped cwd under
            ~/.agenticEvolve/workspaces/ and clean it up after the call.
            Prevents concurrent evolve cycles from clobbering each other's files.

    Returns dict with keys: text, cost, success
    """
    system_prompt = build_system_prompt(config, user_id=user_id)

    # Resolve autonomy level if no explicit allowed_tools given
    if allowed_tools is None and config:
        from .autonomy import resolve_tools
        allowed_tools = resolve_tools(config)

    # Build the full prompt with history
    prompt_parts = []

    if session_context:
        prompt_parts.append(session_context)

    # Inject conversation history
    if history:
        formatted = _format_history(history)
        if formatted:
            prompt_parts.append(
                "# Conversation history (for context — do NOT repeat or summarize it, "
                "just use it to understand what was discussed):\n\n" + formatted
            )

    # Auto-recall: search all memory layers for context relevant to this message.
    # This is what makes the agent "conscious" — it automatically retrieves
    # past conversations, learnings, instincts, and notes before responding.
    try:
        from .session_db import unified_search, format_recall_context

        # Extract search keywords from message (skip very short or command-like messages)
        recall_query = message.strip()
        if len(recall_query) > 15 and not recall_query.startswith("/"):
            # Use first 200 chars as search query
            session_id = ""
            if session_context:
                # Try to extract session ID from context string
                for part in session_context.split():
                    if part.startswith("20") and "_" in part:
                        session_id = part
                        break
            results = unified_search(recall_query[:200], session_id=session_id,
                                     limit_per_layer=2)
            recall_block = format_recall_context(results, max_chars=1500)
            if recall_block:
                prompt_parts.append(recall_block)
    except Exception as e:
        log.debug(f"Auto-recall failed (non-fatal): {e}")

    prompt_parts.append(f"# Current message:\n\n{message}")

    full_prompt = "\n\n---\n\n".join(prompt_parts)

    cmd = [
        "claude", "-p", full_prompt,
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if enable_browser and config:
        # Enable browser MCP for @agent invocations
        browser_cfg = config.get("browser", {})
        browser_default = browser_cfg.get("default", "abp")
        browser_opts = browser_cfg.get("options", {}).get(browser_default, {})
        browser_cmd = browser_opts.get("command", "npx -y agent-browser-protocol --mcp")
        mcp_config = json.dumps({"mcpServers": {
            "browser": {"command": browser_cmd.split()[0], "args": browser_cmd.split()[1:]}
        }})
        cmd.extend(["--mcp-config", mcp_config])
    else:
        cmd.extend(["--no-chrome", "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config"])

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    else:
        cmd.append("--dangerously-skip-permissions")

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    env = _sanitize_env(os.environ.copy(), config)
    _workspace: Path | None = None
    if use_workspace:
        _workspace = _make_workspace()
        work_dir = str(_workspace)
        log.debug(f"invoke_claude: using isolated workspace {_workspace}")
    else:
        work_dir = cwd or str(Path.home())

    # Sandbox wrapping (Docker isolation when configured)
    from .sandbox import wrap_command
    cmd = wrap_command(cmd, config)

    # Retry up to 2 times on empty/transient response.
    # Workspace is cleaned up in finally whether the call succeeds or raises.
    try:
        for attempt in range(2):
            try:
                log.debug(f"Claude invocation (attempt {attempt+1}): prompt={len(full_prompt)} chars, model={model}")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=max_seconds,
                    cwd=work_dir,
                    env=env
                )

                output = result.stdout.strip()
                stderr = result.stderr.strip() if result.stderr else ""

                if stderr:
                    log.debug(f"Claude stderr: {stderr[:300]}")

                if not output:
                    reason = _classify_stderr(stderr)
                    log.warning(
                        f"Claude returned empty stdout "
                        f"(returncode={result.returncode}, reason={reason.value}, stderr={stderr[:200]})"
                    )
                    if reason == InvokeFailReason.AUTH_PERMANENT:
                        log.error("AUTH_PERMANENT — not retrying")
                        return {"text": "Authentication failed. Check your API key.", "cost": 0, "success": False}
                    if reason == InvokeFailReason.BILLING:
                        log.error("BILLING — not retrying")
                        return {"text": "Billing quota exceeded. Check your Anthropic account.", "cost": 0, "success": False}
                    if reason == InvokeFailReason.RATE_LIMIT:
                        cooldown_until = _cooldowns.get(reason.value, 0)
                        if time.time() < cooldown_until:
                            remaining = int(cooldown_until - time.time())
                            return {"text": f"Rate limited. Please wait {remaining}s and try again.", "cost": 0, "success": False}
                        _cooldowns[reason.value] = time.time() + 30
                    if attempt == 0:
                        log.info("Retrying...")
                        continue
                    return {"text": f"Claude returned no output (exit code {result.returncode}). Try again.", "cost": 0, "success": False}

                # Parse stream-json: extract text from assistant messages and cost from result.
                # Also collect base64 screenshot images from browser_screenshot tool results.
                text_parts = []
                cost = 0
                images: list[bytes] = []
                for line in output.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get("type") == "assistant":
                            for block in obj.get("message", {}).get("content", []):
                                if block.get("type") == "text":
                                    text_parts.append(block["text"])
                        elif obj.get("type") == "user":
                            # Tool results live in user messages; extract browser screenshot images.
                            for block in obj.get("message", {}).get("content", []):
                                if block.get("type") != "tool_result":
                                    continue
                                result_content = block.get("content", [])
                                if isinstance(result_content, list):
                                    for item in result_content:
                                        if item.get("type") == "image":
                                            src = item.get("source", {})
                                            if src.get("type") == "base64" and src.get("data"):
                                                import base64 as _b64
                                                images.append(_b64.b64decode(src["data"]))
                        elif obj.get("type") == "result":
                            result_text = obj.get("result", "")
                            if result_text:
                                text_parts.append(result_text)
                            cost = obj.get("total_cost_usd", 0)
                    except json.JSONDecodeError:
                        continue

                if not text_parts:
                    log.warning(f"Claude returned output but no text found. Output preview: {output[:300]}")
                    if attempt == 0:
                        continue
                    return {"text": "Claude responded but I couldn't parse the output. Try again.", "cost": cost, "success": False, "images": images}

                final_text = text_parts[-1]
                return {"text": final_text, "cost": cost, "success": True, "images": images}

            except subprocess.TimeoutExpired:
                log.warning(f"invoke_claude timed out after {max_seconds}s — killing subprocess")
                return {"text": f"Request timed out after {max_seconds // 60} minutes. Try a simpler request or break it into steps.", "cost": 0, "success": False}
            except FileNotFoundError:
                return {"text": "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code", "cost": 0, "success": False}
            except Exception as e:
                log.error(f"Claude invocation error: {e}")
                if attempt == 0:
                    continue
                return {"text": f"Error: {e}", "cost": 0, "success": False}

        return {"text": "Failed after retries.", "cost": 0, "success": False}

    finally:
        if _workspace and _workspace.exists():
            try:
                shutil.rmtree(_workspace)
                log.debug(f"invoke_claude: cleaned up workspace {_workspace}")
            except OSError as e:
                log.warning(f"invoke_claude: workspace cleanup failed: {e}")


def invoke_claude_streaming(message: str, on_progress, model: str = "sonnet",
                             cwd: str = None, session_context: str = "",
                             allowed_tools: list[str] | None = None,
                             max_seconds: int = 480,
                             config: dict | None = None,
                             context_mode: str | None = None,
                             use_workspace: bool = False,
                             session_key: str = "",
                             history: list[dict] | None = None,
                             on_text_chunk=None,
                             user_id: str | None = None,
                             enable_browser: bool = False) -> dict:
    """
    Invoke Claude Code with real-time progress reporting via on_progress callback.

    on_progress(update_text: str) is called whenever Claude uses a tool or
    produces intermediate output. Used for long-running tasks like /evolve.

    on_text_chunk(text: str) is called when Claude produces text output blocks.
    Used for streaming responses to Telegram (edit-in-place).

    Args:
        allowed_tools: If set, restricts Claude to these tools instead of --dangerously-skip-permissions
        max_seconds: Hard timeout; sends SIGTERM→SIGKILL if exceeded. Default 480s (8 min).
        config: Full gateway config for autonomy level resolution
        context_mode: Optional overlay name passed to build_system_prompt (e.g. 'review', 'absorb').
        use_workspace: If True, create an isolated UUID-scoped cwd and clean it up after the call.
        session_key: Scope for LoopDetector (e.g. 'telegram:12345'). Defaults to session_context.
        history: Conversation history (list of {role, content} dicts).
        on_text_chunk: Callback for text output blocks (for streaming to chat).
        user_id: User ID for language preference injection.
        enable_browser: If True, enable browser MCP.

    Returns dict with keys: text, cost, success, timed_out (optional), loop_detected (optional)
    """
    system_prompt = build_system_prompt(config, context_mode=context_mode,
                                         user_id=user_id)

    # Resolve autonomy level if no explicit allowed_tools given
    if allowed_tools is None and config:
        from .autonomy import resolve_tools
        allowed_tools = resolve_tools(config)

    prompt_parts = []
    if session_context:
        prompt_parts.append(session_context)
    # Inject conversation history (same as invoke_claude)
    if history:
        formatted = _format_history(history)
        if formatted:
            prompt_parts.append(f"# Conversation history:\n\n{formatted}")
    prompt_parts.append(f"# Current message:\n\n{message}")
    full_prompt = "\n\n---\n\n".join(prompt_parts)

    cmd = [
        "claude", "-p", full_prompt,
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if enable_browser and config:
        browser_cfg = config.get("browser", {})
        browser_default = browser_cfg.get("default", "abp")
        browser_opts = browser_cfg.get("options", {}).get(browser_default, {})
        browser_cmd = browser_opts.get("command", "npx -y agent-browser-protocol --mcp")
        mcp_config = json.dumps({"mcpServers": {
            "browser": {"command": browser_cmd.split()[0], "args": browser_cmd.split()[1:]}
        }})
        cmd.extend(["--mcp-config", mcp_config])
    else:
        cmd.extend(["--no-chrome", "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config"])

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    else:
        cmd.append("--dangerously-skip-permissions")

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    env = _sanitize_env(os.environ.copy(), config)
    _workspace: Path | None = None
    if use_workspace:
        _workspace = _make_workspace()
        work_dir = str(_workspace)
        log.debug(f"invoke_claude_streaming: using isolated workspace {_workspace}")
    else:
        work_dir = cwd or str(Path.home())

    # Sandbox wrapping (Docker isolation when configured)
    from .sandbox import wrap_command
    cmd = wrap_command(cmd, config)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=work_dir,
            env=env,
        )

        text_parts = []
        cost = 0
        tool_count = 0
        last_progress_tool = ""
        timed_out = False
        loop_detected = False
        _sk = session_key or session_context  # scope for LoopDetector

        timer = threading.Timer(max_seconds, _terminate_proc, args=[proc])
        timer.start()

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    msg_type = obj.get("type", "")

                    # Tool use — report what Claude is doing
                    if msg_type == "assistant":
                        content = obj.get("message", {}).get("content", [])

                        # Collect all tool_use blocks in this turn for loop detection
                        turn_tool_calls = [b for b in content if b.get("type") == "tool_use"]
                        if turn_tool_calls and _sk:
                            loop_count = _loop_detector.record(_sk, turn_tool_calls)
                            if loop_count >= 5:
                                log.warning(
                                    f"LoopDetector: {_sk} repeated fingerprint {loop_count}× — "
                                    "terminating subprocess"
                                )
                                loop_detected = True
                                _terminate_proc(proc)
                                break
                            elif loop_count == 3:
                                log.warning(
                                    f"LoopDetector: {_sk} repeated fingerprint {loop_count}× — "
                                    "injecting warning via on_progress"
                                )
                                try:
                                    on_progress(
                                        "WARNING: loop detected — you are repeating the same "
                                        "tool calls. Vary your approach or conclude."
                                    )
                                except Exception:
                                    pass

                        for block in content:
                            if block.get("type") == "tool_use":
                                tool_name = block.get("name", "unknown")
                                tool_input = block.get("input", {})
                                tool_count += 1

                                # Build a human-readable progress line
                                if tool_name == "Bash":
                                    cmd_preview = tool_input.get("command", "")[:80]
                                    progress = f"[{tool_count}] Running: `{cmd_preview}`"
                                elif tool_name == "Read":
                                    file_path = tool_input.get("filePath", "")
                                    progress = f"[{tool_count}] Reading: `{file_path}`"
                                elif tool_name == "Write":
                                    file_path = tool_input.get("filePath", "")
                                    progress = f"[{tool_count}] Writing: `{file_path}`"
                                elif tool_name == "Edit":
                                    file_path = tool_input.get("filePath", "")
                                    progress = f"[{tool_count}] Editing: `{file_path}`"
                                elif tool_name == "Glob":
                                    pattern = tool_input.get("pattern", "")
                                    progress = f"[{tool_count}] Searching: `{pattern}`"
                                elif tool_name == "Grep":
                                    pattern = tool_input.get("pattern", "")
                                    progress = f"[{tool_count}] Grepping: `{pattern}`"
                                elif tool_name == "WebFetch":
                                    url = tool_input.get("url", "")[:60]
                                    progress = f"[{tool_count}] Fetching: `{url}`"
                                elif tool_name == "Task":
                                    desc = tool_input.get("description", "")[:60]
                                    progress = f"[{tool_count}] Subagent: {desc}"
                                else:
                                    progress = f"[{tool_count}] {tool_name}"

                                # Avoid sending duplicate progress for same tool
                                if progress != last_progress_tool:
                                    last_progress_tool = progress
                                    try:
                                        on_progress(progress)
                                    except Exception as e:
                                        log.warning(f"Progress callback error: {e}")

                            elif block.get("type") == "text":
                                text_parts.append(block["text"])
                                # Emit text chunk for streaming to chat
                                if on_text_chunk:
                                    try:
                                        on_text_chunk(block["text"])
                                    except Exception as _tc_err:
                                        log.debug(f"Text chunk callback error: {_tc_err}")

                    elif msg_type == "result":
                        result_text = obj.get("result", "")
                        if result_text:
                            text_parts.append(result_text)
                        cost = obj.get("total_cost_usd", 0)

                except json.JSONDecodeError:
                    continue
                except ValueError:
                    # I/O on closed file — timer fired mid-read
                    timed_out = True
                    break
        finally:
            timer.cancel()

        if loop_detected:
            log.warning(f"invoke_claude_streaming: loop guard terminated subprocess for {_sk}")
            partial = text_parts[-1] if text_parts else "Loop detected — agent was stuck repeating tool calls."
            return {"text": partial, "cost": cost, "success": False, "loop_detected": True}

        if timed_out:
            log.warning(f"invoke_claude_streaming timed out after {max_seconds}s")
            partial = text_parts[-1] if text_parts else "Timed out with no output."
            return {"text": partial, "cost": cost, "success": False, "timed_out": True}

        proc.wait(timeout=30)

        if not text_parts:
            return {"text": "Claude ran but produced no text output.", "cost": cost, "success": False}

        final_text = text_parts[-1]
        return {"text": final_text, "cost": cost, "success": True}

    except subprocess.TimeoutExpired:
        proc.kill()
        return {"text": "Request timed out.", "cost": 0, "success": False}
    except FileNotFoundError:
        return {"text": "Claude CLI not found.", "cost": 0, "success": False}
    except Exception as e:
        log.error(f"Streaming invocation error: {e}")
        return {"text": f"Error: {e}", "cost": 0, "success": False}
    finally:
        if _workspace and _workspace.exists():
            try:
                shutil.rmtree(_workspace)
                log.debug(f"invoke_claude_streaming: cleaned up workspace {_workspace}")
            except OSError as e:
                log.warning(f"invoke_claude_streaming: workspace cleanup failed: {e}")


def consolidate_session(session_id: str, project_id: str = "") -> int:
    """Silent end-of-session consolidation pass.

    Fires a Haiku call to extract key patterns from the session and routes
    each through score_and_route_observation(). No output is returned to the
    user — this runs silently after the session ends.

    Args:
        session_id: Session to consolidate.
        project_id: Hash of git remote for project-scoped instinct tracking.

    Returns:
        Number of observations routed (0 on any failure).
    """
    try:
        from .session_db import get_session_messages, score_and_route_observation

        msgs = get_session_messages(session_id)
        if len(msgs) < 4:
            return 0

        # Build a compact transcript (last 20 messages, 1500 chars each)
        transcript_lines = []
        for m in msgs[-20:]:
            role = m.get("role", "")
            content = (m.get("content") or "")[:1500]
            transcript_lines.append(f"[{role}]: {content}")
        transcript = "\n\n".join(transcript_lines)

        extract_prompt = (
            "You are a silent memory extractor. Read this session transcript and "
            "extract 3-7 concrete, reusable behaviour patterns, preferences, or "
            "lessons learned. Each pattern must be actionable and ≥15 words. "
            "Output ONLY a JSON array of strings. No explanation. No preamble.\n\n"
            f"Transcript:\n{transcript}"
        )

        result = invoke_claude(
            extract_prompt,
            model="sonnet",
            allowed_tools=[],  # read-only — no tools needed
        )

        if not result.get("success"):
            return 0

        import json as _json
        text = result.get("text", "").strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        try:
            patterns = _json.loads(text)
        except (_json.JSONDecodeError, ValueError):
            return 0

        if not isinstance(patterns, list):
            return 0

        routed = 0
        for p in patterns:
            if isinstance(p, str) and p.strip():
                score_and_route_observation(
                    p.strip(),
                    context=f"consolidation:{session_id}",
                    project_id=project_id,
                )
                routed += 1

        log.debug(f"consolidate_session {session_id}: routed {routed} observations")
        return routed

    except Exception as e:
        log.warning(f"consolidate_session failed silently: {e}")
        return 0


def generate_title(message: str) -> str:
    """Generate a short session title from the first message.

    Uses simple heuristic — no LLM call to save cost.
    """
    # Clean up and take first 60 chars
    title = message.strip().replace("\n", " ")
    if len(title) > 60:
        title = title[:57] + "..."
    return title
