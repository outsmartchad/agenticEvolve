"""Claude Code invocation wrapper for the gateway."""
import json
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

log = logging.getLogger("agenticEvolve.agent")

EXODIR = Path.home() / ".agenticEvolve"


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
                        context_mode: str | None = None) -> str:
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
    mem_path = EXODIR / "memory" / "MEMORY.md"
    if mem_path.exists():
        mem = mem_path.read_text().strip()
        chars = len(mem)
        pct = int(chars / 2200 * 100)
        parts.append(
            f"# MEMORY (your personal notes) [{pct}% — {chars}/2,200 chars]\n{mem}"
        )

    # USER.md — user profile
    user_path = EXODIR / "memory" / "USER.md"
    if user_path.exists():
        user = user_path.read_text().strip()
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


def invoke_claude(message: str, model: str = "sonnet",
                   cwd: str = None, history: list[dict] = None,
                   session_context: str = "",
                   allowed_tools: list[str] | None = None,
                   config: dict | None = None) -> dict:
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

    Returns dict with keys: text, cost, success
    """
    system_prompt = build_system_prompt(config)

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
    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    else:
        cmd.append("--dangerously-skip-permissions")

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    env = os.environ.copy()
    work_dir = cwd or str(Path.home())

    # Retry up to 2 times on empty/transient response
    for attempt in range(2):
        try:
            log.debug(f"Claude invocation (attempt {attempt+1}): prompt={len(full_prompt)} chars, model={model}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
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

            # Parse stream-json: extract text from assistant messages and cost from result
            text_parts = []
            cost = 0
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
                return {"text": "Claude responded but I couldn't parse the output. Try again.", "cost": cost, "success": False}

            final_text = text_parts[-1]
            return {"text": final_text, "cost": cost, "success": True}

        except subprocess.TimeoutExpired:
            return {"text": "Request timed out (5 min limit).", "cost": 0, "success": False}
        except FileNotFoundError:
            return {"text": "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code", "cost": 0, "success": False}
        except Exception as e:
            log.error(f"Claude invocation error: {e}")
            if attempt == 0:
                continue
            return {"text": f"Error: {e}", "cost": 0, "success": False}

    return {"text": "Failed after retries.", "cost": 0, "success": False}


def invoke_claude_streaming(message: str, on_progress, model: str = "sonnet",
                             cwd: str = None, session_context: str = "",
                             allowed_tools: list[str] | None = None,
                             max_seconds: int = 480,
                             config: dict | None = None,
                             context_mode: str | None = None) -> dict:
    """
    Invoke Claude Code with real-time progress reporting via on_progress callback.

    on_progress(update_text: str) is called whenever Claude uses a tool or
    produces intermediate output. Used for long-running tasks like /evolve.

    Args:
        allowed_tools: If set, restricts Claude to these tools instead of --dangerously-skip-permissions
        max_seconds: Hard timeout; sends SIGTERM→SIGKILL if exceeded. Default 480s (8 min).
        config: Full gateway config for autonomy level resolution
        context_mode: Optional overlay name passed to build_system_prompt (e.g. 'review', 'absorb').

    Returns dict with keys: text, cost, success, timed_out (optional)
    """
    system_prompt = build_system_prompt(config, context_mode=context_mode)

    # Resolve autonomy level if no explicit allowed_tools given
    if allowed_tools is None and config:
        from .autonomy import resolve_tools
        allowed_tools = resolve_tools(config)

    prompt_parts = []
    if session_context:
        prompt_parts.append(session_context)
    prompt_parts.append(f"# Current message:\n\n{message}")
    full_prompt = "\n\n---\n\n".join(prompt_parts)

    cmd = [
        "claude", "-p", full_prompt,
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    else:
        cmd.append("--dangerously-skip-permissions")

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    env = os.environ.copy()
    work_dir = cwd or str(Path.home())

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
            model="haiku",
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
