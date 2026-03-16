"""
ae chat — Interactive CLI REPL for agenticEvolve.

Rich-based TUI with streaming output, markdown rendering, session management,
and all slash commands. Standalone — does not require the gateway process.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion

# ── Bootstrap ───────────────────────────────────────────────────

EXODIR = Path.home() / ".agenticEvolve"
# Ensure gateway package is importable
sys.path.insert(0, str(EXODIR))

from gateway.config import load_config
from gateway.agent import (
    build_system_prompt,
    invoke_claude,
    get_today_cost,
    get_week_cost,
    generate_title,
    _format_history,
    EXODIR as AGENT_EXODIR,
)
from gateway.session_db import (
    generate_session_id,
    create_session,
    add_message,
    end_session,
    get_session_messages,
    set_title,
    list_sessions,
    search_sessions,
    stats,
    log_cost,
    unified_search,
    format_recall_context,
)

console = Console()

# ── Session State ───────────────────────────────────────────────

class SessionState:
    """Tracks the active chat session."""

    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "sonnet")
        self.session_id: str = ""
        self.history: list[dict] = []
        self.message_count: int = 0
        self.session_cost: float = 0.0
        self.new_session()

    def new_session(self):
        """Start a fresh session."""
        if self.session_id and self.message_count > 0:
            end_session(self.session_id)
        self.session_id = generate_session_id()
        create_session(self.session_id, source="cli", model=self.model)
        self.history = []
        self.message_count = 0
        self.session_cost = 0.0

    def add_user_message(self, text: str):
        add_message(self.session_id, "user", text)
        self.history.append({"role": "user", "content": text})
        self.message_count += 1
        if self.message_count == 1:
            title = generate_title(text)
            set_title(self.session_id, title)

    def add_assistant_message(self, text: str, cost: float):
        add_message(self.session_id, "assistant", text)
        self.history.append({"role": "assistant", "content": text})
        self.message_count += 1
        self.session_cost += cost
        if cost > 0:
            log_cost(cost, platform="cli", session_id=self.session_id)

    def end(self):
        if self.session_id and self.message_count > 0:
            end_session(self.session_id)


# ── Streaming Invocation ────────────────────────────────────────

def invoke_streaming(message: str, state: SessionState) -> dict:
    """Invoke Claude Code with real-time streaming to the terminal.

    Parses stream-json output line by line, rendering assistant text
    blocks as they arrive and showing tool use with spinners.

    Returns {"text": str, "cost": float, "success": bool}
    """
    config = state.config
    system_prompt = build_system_prompt(config)

    # Resolve allowed tools
    allowed_tools = None
    try:
        from gateway.autonomy import resolve_tools
        allowed_tools = resolve_tools(config)
    except Exception:
        pass

    # Build prompt with history + auto-recall
    prompt_parts = []
    ctx = f"[Gateway: platform=cli, session={state.session_id}]"
    prompt_parts.append(ctx)

    if state.history:
        formatted = _format_history(state.history)
        if formatted:
            prompt_parts.append(
                "# Conversation history (for context — do NOT repeat or summarize it, "
                "just use it to understand what was discussed):\n\n" + formatted
            )

    # Auto-recall
    try:
        recall_query = message.strip()
        if len(recall_query) > 15 and not recall_query.startswith("/"):
            results = unified_search(recall_query[:200], session_id=state.session_id,
                                     limit_per_layer=2)
            recall_block = format_recall_context(results, max_chars=1500)
            if recall_block:
                prompt_parts.append(recall_block)
    except Exception:
        pass

    prompt_parts.append(f"# Current message:\n\n{message}")
    full_prompt = "\n\n---\n\n".join(prompt_parts)

    cmd = [
        "claude", "-p", full_prompt,
        "--model", state.model,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    else:
        cmd.append("--dangerously-skip-permissions")

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    # Sandbox wrapping
    try:
        from gateway.sandbox import wrap_command
        cmd = wrap_command(cmd, config)
    except Exception:
        pass

    env = os.environ.copy()
    work_dir = str(Path.home())

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=work_dir,
        env=env,
    )

    text_parts = []
    cost = 0.0
    current_text = ""
    tool_name = ""

    # Timer for timeout
    max_seconds = 600
    timed_out = False

    def _timeout():
        nonlocal timed_out
        timed_out = True
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    timer = threading.Timer(max_seconds, _timeout)
    timer.start()

    try:
        # Track whether we're currently showing a tool spinner
        active_spinner = None
        live = None

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                msg_type = obj.get("type", "")

                if msg_type == "assistant":
                    content = obj.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            text = block["text"]
                            text_parts.append(text)
                            # Stop any active spinner before printing text
                            if live:
                                live.stop()
                                live = None
                            # Render markdown
                            console.print(Markdown(text))

                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "tool")
                            tool_input = block.get("input", {})
                            # Show tool description
                            desc = _tool_description(tool_name, tool_input)
                            if live:
                                live.stop()
                            live = Live(
                                Spinner("dots", text=Text(f" {desc}", style="dim")),
                                console=console,
                                transient=True,
                            )
                            live.start()

                elif msg_type == "user":
                    # Tool results — stop spinner
                    if live:
                        live.stop()
                        live = None

                elif msg_type == "result":
                    # Result object contains the final text + cost.
                    # Text was already printed from assistant blocks — only extract cost.
                    result_text = obj.get("result", "")
                    if result_text and not text_parts:
                        # Only print if we somehow missed assistant blocks
                        text_parts.append(result_text)
                        if live:
                            live.stop()
                            live = None
                        console.print(Markdown(result_text))
                    elif result_text:
                        # Update final text for session storage (result is authoritative)
                        text_parts[-1] = result_text
                    cost = obj.get("total_cost_usd", 0)

            except json.JSONDecodeError:
                continue

        if live:
            live.stop()

        proc.wait()

    finally:
        timer.cancel()
        try:
            proc.kill()
        except Exception:
            pass

    if timed_out:
        console.print("[red]Request timed out.[/red]")
        return {"text": "Timed out.", "cost": cost, "success": False}

    if not text_parts:
        stderr = proc.stderr.read() if proc.stderr else ""
        console.print(f"[red]No response from Claude.[/red]")
        if stderr:
            console.print(f"[dim]{stderr[:200]}[/dim]")
        return {"text": "", "cost": cost, "success": False}

    final_text = text_parts[-1]
    return {"text": final_text, "cost": cost, "success": True}


def _tool_description(name: str, input_data: dict) -> str:
    """One-liner description of a tool call for the spinner."""
    if name == "Read":
        fp = input_data.get("file_path") or input_data.get("filePath", "")
        return f"Reading {Path(fp).name}" if fp else "Reading file"
    if name == "Write":
        fp = input_data.get("file_path") or input_data.get("filePath", "")
        return f"Writing {Path(fp).name}" if fp else "Writing file"
    if name == "Edit":
        fp = input_data.get("file_path") or input_data.get("filePath", "")
        return f"Editing {Path(fp).name}" if fp else "Editing file"
    if name == "Bash":
        cmd = input_data.get("command", "")
        return f"Running: {cmd[:60]}" if cmd else "Running command"
    if name in ("Glob", "Search"):
        pattern = input_data.get("pattern", "")
        return f"Searching: {pattern}" if pattern else "Searching files"
    if name == "Grep":
        pattern = input_data.get("pattern", "")
        return f"Grep: {pattern[:40]}" if pattern else "Searching content"
    if name == "WebFetch":
        url = input_data.get("url", "")
        return f"Fetching: {url[:50]}" if url else "Fetching URL"
    if name == "Task":
        desc = input_data.get("description", "")
        return f"Agent: {desc}" if desc else "Running sub-agent"
    return f"Using {name}"


# ── Slash Commands ──────────────────────────────────────────────

SLASH_COMMANDS = [
    ("/help", "Show available commands"),
    ("/new", "Start a new session"),
    ("/cost", "Show cost breakdown"),
    ("/model", "Show or switch model (e.g. /model opus)"),
    ("/sessions", "List recent sessions (e.g. /sessions 10)"),
    ("/search", "Search past conversations (e.g. /search LID JID)"),
    ("/memory", "Show MEMORY.md"),
    ("/status", "System status overview"),
    ("/quit", "Exit the REPL"),
]


class SlashCompleter(Completer):
    """Auto-complete slash commands with descriptions."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        # Only complete if the line starts with /
        if not text.startswith("/"):
            return
        # Don't complete if there's already a space (user is typing args)
        if " " in text:
            return
        for cmd, desc in SLASH_COMMANDS:
            if cmd.startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display_meta=desc,
                )


def handle_command(cmd: str, state: SessionState) -> bool:
    """Handle a slash command. Returns True if handled, False if not a command."""
    parts = cmd.strip().split(None, 1)
    name = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if name in ("/help", "/h", "/?"):
        _cmd_help()
    elif name in ("/new", "/newsession"):
        _cmd_new(state)
    elif name in ("/cost", "/c"):
        _cmd_cost(state)
    elif name in ("/model", "/m"):
        _cmd_model(state, arg)
    elif name in ("/sessions", "/s"):
        _cmd_sessions(arg)
    elif name in ("/search",):
        _cmd_search(arg)
    elif name in ("/memory", "/mem"):
        _cmd_memory()
    elif name in ("/status",):
        _cmd_status(state)
    elif name in ("/quit", "/q", "/exit"):
        return _cmd_quit(state)
    else:
        console.print(f"[yellow]Unknown command: {name}[/yellow]")
        console.print("[dim]Type /help for available commands[/dim]")
    return True


def _cmd_help():
    help_text = """
**Commands**

| Command | Description |
|---------|-------------|
| `/help` | Show this help |
| `/new` | Start a new session |
| `/cost` | Show cost breakdown |
| `/model [name]` | Show or switch model |
| `/sessions [N]` | List recent sessions |
| `/search <query>` | Search past conversations |
| `/memory` | Show MEMORY.md |
| `/status` | System status |
| `/quit` | Exit |

**Tips**: Ctrl+C to interrupt generation, Ctrl+D to exit.
"""
    console.print(Markdown(help_text))


def _cmd_new(state: SessionState):
    state.new_session()
    console.print("[green]New session started.[/green]")
    console.print(f"[dim]Session: {state.session_id}[/dim]")


def _cmd_cost(state: SessionState):
    today = get_today_cost()
    week = get_week_cost()
    cap_day = state.config.get("daily_cost_cap", 5.0)
    cap_week = state.config.get("weekly_cost_cap", 25.0)

    table = Table(title="Cost", show_header=True, header_style="bold")
    table.add_column("Period", style="cyan")
    table.add_column("Spent", justify="right")
    table.add_column("Cap", justify="right")
    table.add_column("Remaining", justify="right")
    table.add_row("This session", f"${state.session_cost:.4f}", "-", "-")
    table.add_row("Today", f"${today:.4f}", f"${cap_day:.2f}", f"${max(0, cap_day - today):.2f}")
    table.add_row("This week", f"${week:.4f}", f"${cap_week:.2f}", f"${max(0, cap_week - week):.2f}")
    console.print(table)


def _cmd_model(state: SessionState, arg: str):
    if not arg:
        console.print(f"Current model: [bold]{state.model}[/bold]")
        console.print("[dim]Usage: /model <name> (e.g. sonnet, opus, haiku)[/dim]")
        return
    state.model = arg.strip()
    console.print(f"Model set to: [bold]{state.model}[/bold]")


def _cmd_sessions(arg: str):
    limit = int(arg) if arg.isdigit() else 10
    sessions = list_sessions(limit=limit)
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Recent Sessions", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", max_width=25)
    table.add_column("Source", max_width=10)
    table.add_column("Title", max_width=40)
    table.add_column("Messages", justify="right")
    table.add_column("Started", max_width=20)

    for s in sessions:
        started = s.get("started_at", "")[:16] if s.get("started_at") else "-"
        table.add_row(
            s.get("id", ""),
            s.get("source", ""),
            (s.get("title") or "-")[:40],
            str(s.get("message_count", 0)),
            started,
        )
    console.print(table)


def _cmd_search(arg: str):
    if not arg:
        console.print("[yellow]Usage: /search <query>[/yellow]")
        return
    results = search_sessions(arg, limit=5)
    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    for r in results:
        title = r.get("title") or r.get("session_id", "")
        snippet = r.get("snippet", "")[:100]
        console.print(f"[cyan]{title}[/cyan]")
        console.print(f"  [dim]{snippet}...[/dim]")
        console.print()


def _cmd_memory():
    mem_path = EXODIR / "memory" / "MEMORY.md"
    if mem_path.exists():
        content = mem_path.read_text().strip()
        chars = len(content)
        pct = int(chars / 2200 * 100)
        console.print(Panel(
            Markdown(content),
            title=f"MEMORY.md [{pct}% — {chars}/2,200 chars]",
            border_style="cyan",
        ))
    else:
        console.print("[dim]No MEMORY.md found.[/dim]")


def _cmd_status(state: SessionState):
    st = stats()
    today = get_today_cost()

    table = Table(title="Status", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Session", state.session_id)
    table.add_row("Model", state.model)
    table.add_row("Messages", str(state.message_count))
    table.add_row("Session cost", f"${state.session_cost:.4f}")
    table.add_row("Today cost", f"${today:.4f}")
    table.add_row("Total sessions", str(st.get("total_sessions", 0)))
    table.add_row("Total messages", str(st.get("total_messages", 0)))
    table.add_row("DB size", f"{st.get('db_size_mb', 0)} MB")
    console.print(table)


def _cmd_quit(state: SessionState) -> bool:
    """Returns True to signal exit."""
    state.end()
    console.print("[dim]Session ended. Goodbye.[/dim]")
    raise SystemExit(0)


# ── Cost Cap Check ──────────────────────────────────────────────

def check_cost_cap(config: dict) -> str | None:
    """Returns warning message if cost cap exceeded, else None."""
    today = get_today_cost()
    week = get_week_cost()
    cap_day = config.get("daily_cost_cap", 5.0)
    cap_week = config.get("weekly_cost_cap", 25.0)
    if today >= cap_day:
        return f"Daily cost cap reached (${today:.2f} / ${cap_day:.2f})"
    if week >= cap_week:
        return f"Weekly cost cap reached (${week:.2f} / ${cap_week:.2f})"
    return None


# ── Main REPL ───────────────────────────────────────────────────

def main(resume_session: str = None):
    """Entry point for ae chat."""
    config = load_config()
    state = SessionState(config)

    # Resume a previous session if requested
    if resume_session:
        messages = get_session_messages(resume_session)
        if messages:
            state.session_id = resume_session
            state.history = [{"role": m["role"], "content": m["content"]} for m in messages]
            state.message_count = len(messages)
            console.print(f"[green]Resumed session: {resume_session}[/green]")
            console.print(f"[dim]{state.message_count} messages loaded[/dim]")
        else:
            console.print(f"[yellow]Session {resume_session} not found, starting new.[/yellow]")

    # Banner
    console.print()
    console.print(
        Panel(
            "[bold]agenticEvolve[/bold] interactive chat\n"
            f"[dim]Model: {state.model} | Session: {state.session_id}[/dim]\n"
            "[dim]Type /help for commands, Ctrl+D to exit[/dim]",
            border_style="blue",
        )
    )
    console.print()

    # Input with history
    history_file = EXODIR / ".cli_history"
    prompt_session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=SlashCompleter(),
        complete_while_typing=True,
    )

    while True:
        try:
            # Multi-line: if user types \ at end, continue
            user_input = prompt_session.prompt(
                "you> ",
                multiline=False,
            ).strip()

            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                handle_command(user_input, state)
                continue

            # Cost cap check
            cap_msg = check_cost_cap(config)
            if cap_msg:
                console.print(f"[red]{cap_msg}[/red]")
                continue

            # Persist user message
            state.add_user_message(user_input)

            # Invoke Claude with streaming
            console.print()
            result = invoke_streaming(user_input, state)
            console.print()

            if result["success"]:
                state.add_assistant_message(result["text"], result["cost"])
                if result["cost"] > 0:
                    console.print(
                        f"[dim]${result['cost']:.4f} | "
                        f"session: ${state.session_cost:.4f}[/dim]"
                    )
            else:
                console.print("[red]Request failed.[/red]")

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Type /quit to exit.[/dim]")
            continue
        except EOFError:
            # Ctrl+D
            state.end()
            console.print("\n[dim]Session ended. Goodbye.[/dim]")
            break


if __name__ == "__main__":
    main()
