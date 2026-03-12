"""Claude Code invocation wrapper for the gateway."""
import subprocess
import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("agenticEvolve.agent")

EXODIR = Path.home() / ".agenticEvolve"


def build_system_prompt() -> str:
    """Assemble system prompt from SOUL.md + MEMORY.md + USER.md."""
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
    """Read today's total cost from cost.log."""
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


def invoke_claude(message: str, model: str = "sonnet",
                  cwd: str = None, history: list[dict] = None,
                  session_context: str = "") -> dict:
    """
    Invoke Claude Code with a message and return the response.

    Args:
        message: The user's message
        model: Model to use (sonnet, opus, etc.)
        cwd: Working directory for Claude Code
        history: List of past messages [{"role": "user/assistant", "content": "..."}]
        session_context: Extra context line (platform, session id, etc.)

    Returns dict with keys: text, cost, success
    """
    system_prompt = build_system_prompt()

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
        "--dangerously-skip-permissions",
    ]

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


def generate_title(message: str) -> str:
    """Generate a short session title from the first message.

    Uses simple heuristic — no LLM call to save cost.
    """
    # Clean up and take first 60 chars
    title = message.strip().replace("\n", " ")
    if len(title) > 60:
        title = title[:57] + "..."
    return title
