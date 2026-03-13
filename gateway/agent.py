"""Claude Code invocation wrapper for the gateway."""
import json
import logging
import os
import signal
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("agenticEvolve.agent")

EXODIR = Path.home() / ".agenticEvolve"


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

    Takes the most recent `max_turns` messages, truncates to `max_chars` total.
    """
    if not history:
        return ""

    # Take last N turns
    recent = history[-max_turns:]

    lines = []
    total = 0
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Truncate individual messages that are too long
        if len(content) > 1500:
            content = content[:1500] + "... [truncated]"
        line = f"[{role}]: {content}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)

    return "\n\n".join(lines)


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

    # Retry up to 2 times on empty response
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
                log.warning(f"Claude returned empty stdout (returncode={result.returncode}, stderr={stderr[:200]})")
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


def generate_title(message: str) -> str:
    """Generate a short session title from the first message.

    Uses simple heuristic — no LLM call to save cost.
    """
    # Clean up and take first 60 chars
    title = message.strip().replace("\n", " ")
    if len(title) > 60:
        title = title[:57] + "..."
    return title
