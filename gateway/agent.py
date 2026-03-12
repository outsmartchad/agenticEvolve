"""Claude Code invocation wrapper for the gateway."""
import subprocess
import json
import os
from pathlib import Path

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


def invoke_claude(message: str, model: str = "sonnet",
                  cwd: str = None) -> dict:
    """
    Invoke Claude Code with a message and return the response.

    Returns dict with keys: text, cost, success
    """
    system_prompt = build_system_prompt()

    cmd = [
        "claude", "-p", message,
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    env = os.environ.copy()
    work_dir = cwd or str(Path.home())

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=work_dir,
            env=env
        )

        output = result.stdout.strip()
        if not output:
            return {"text": "No response from Claude.", "cost": 0, "success": False}

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
                    text_parts.append(obj.get("result", ""))
                    cost = obj.get("total_cost_usd", 0)
            except json.JSONDecodeError:
                continue

        final_text = text_parts[-1] if text_parts else "No response."
        return {"text": final_text, "cost": cost, "success": True}

    except subprocess.TimeoutExpired:
        return {"text": "Request timed out (5 min limit).", "cost": 0, "success": False}
    except FileNotFoundError:
        return {"text": "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code", "cost": 0, "success": False}
    except Exception as e:
        return {"text": f"Error: {e}", "cost": 0, "success": False}
