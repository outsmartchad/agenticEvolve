"""
ae — Interactive CLI REPL for agenticEvolve.

Rich-based TUI with streaming output, markdown rendering, session management,
and all gateway commands. Standalone — does not require the gateway process.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
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
CRON_DIR = EXODIR / "cron"
CRON_JOBS_FILE = CRON_DIR / "jobs.json"

sys.path.insert(0, str(EXODIR))

from gateway.config import load_config, CONFIG_PATH
from gateway.agent import (
    build_system_prompt,
    invoke_claude_streaming as _invoke_claude_streaming,
    get_today_cost,
    get_week_cost,
    generate_title,
    _format_history,
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
    """Invoke Claude Code with real-time streaming to the terminal."""
    config = state.config
    system_prompt = build_system_prompt(config)

    allowed_tools = None
    try:
        from gateway.autonomy import resolve_tools
        allowed_tools = resolve_tools(config)
    except Exception:
        pass

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

    try:
        from gateway.sandbox import wrap_command
        cmd = wrap_command(cmd, config)
    except Exception:
        pass

    env = os.environ.copy()
    work_dir = str(Path.home())

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=work_dir, env=env,
    )

    text_parts = []
    cost = 0.0
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
                            if live:
                                live.stop()
                                live = None
                            console.print(Markdown(text))
                        elif block.get("type") == "tool_use":
                            desc = _tool_description(block.get("name", "tool"), block.get("input", {}))
                            if live:
                                live.stop()
                            live = Live(
                                Spinner("dots", text=Text(f" {desc}", style="dim")),
                                console=console, transient=True,
                            )
                            live.start()

                elif msg_type == "user":
                    if live:
                        live.stop()
                        live = None

                elif msg_type == "result":
                    result_text = obj.get("result", "")
                    if result_text and not text_parts:
                        text_parts.append(result_text)
                        if live:
                            live.stop()
                            live = None
                        console.print(Markdown(result_text))
                    elif result_text:
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
        console.print("[red]No response from Claude.[/red]")
        if stderr:
            console.print(f"[dim]{stderr[:200]}[/dim]")
        return {"text": "", "cost": cost, "success": False}

    return {"text": text_parts[-1], "cost": cost, "success": True}


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


# ── CLI progress callback for pipelines ─────────────────────────

def _cli_progress(msg: str):
    """Print pipeline progress updates with dim styling."""
    console.print(f"[dim]  {msg}[/dim]")


# ── Slash Commands ──────────────────────────────────────────────

SLASH_COMMANDS = [
    # Session
    ("/help", "Show available commands"),
    ("/new", "Start a new session"),
    ("/quit", "Exit the REPL"),
    # Info
    ("/cost", "Show cost breakdown"),
    ("/model", "Show or switch model (e.g. /model opus)"),
    ("/status", "System status overview"),
    ("/memory", "Show MEMORY.md + USER.md"),
    ("/soul", "Show SOUL.md personality"),
    ("/config", "Show config.yaml settings"),
    ("/sessions", "List recent sessions (e.g. /sessions 10)"),
    ("/search", "Search past conversations"),
    ("/recall", "Search all memory layers"),
    ("/skills", "List installed skills"),
    ("/learnings", "List past learnings"),
    ("/heartbeat", "Quick health check"),
    # Pipelines (LLM-backed)
    ("/produce", "Brainstorm business ideas from signals"),
    ("/evolve", "Run evolve pipeline (COLLECT->ANALYZE->BUILD->REVIEW->REPORT)"),
    ("/learn", "Deep-dive a repo/URL/tech"),
    ("/absorb", "Scan + implement improvements from a target"),
    ("/reflect", "Self-analysis (patterns, gaps, next actions)"),
    ("/digest", "Morning briefing (sessions, signals, cost)"),
    ("/gc", "Garbage collection (stale sessions, orphans)"),
    # Cron
    ("/loop", "Create a recurring cron job"),
    ("/loops", "List active cron jobs"),
    ("/unloop", "Remove a cron job"),
    ("/pause", "Pause a cron job (or --all)"),
    ("/unpause", "Resume a cron job (or --all)"),
    ("/notify", "One-shot delayed notification"),
    # Approval
    ("/queue", "Show skills pending approval"),
    ("/approve", "Approve a queued skill"),
    ("/reject", "Reject a queued skill"),
    # Admin
    ("/autonomy", "Show or set autonomy level"),
]


class SlashCompleter(Completer):
    """Auto-complete slash commands with descriptions."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        if " " in text:
            return
        for cmd, desc in SLASH_COMMANDS:
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display_meta=desc)


def _parse_flags(args: list[str], spec: dict) -> dict:
    """Parse flags from args list. Minimal re-implementation of the gateway's _parse_flags."""
    result = {}
    for flag, info in spec.items():
        aliases = info.get("aliases", [])
        all_names = [flag] + [f"--{a}" if not a.startswith("--") else a for a in aliases]
        if info.get("type") == "bool":
            result[flag] = False
            for name in all_names:
                if name in args:
                    result[flag] = True
                    args.remove(name)
        elif info.get("type") == "value":
            cast_fn = info.get("cast", str)
            result[flag] = info.get("default", "")
            for name in all_names:
                if name in args:
                    idx = args.index(name)
                    if idx + 1 < len(args):
                        try:
                            result[flag] = cast_fn(args[idx + 1])
                        except (ValueError, TypeError):
                            result[flag] = info.get("default", "")
                        args.pop(idx + 1)
                    args.pop(idx)
                    break
    return result


def handle_command(cmd: str, state: SessionState) -> bool:
    """Handle a slash command. Returns True if handled."""
    parts = cmd.strip().split(None, 1)
    name = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # ── Session ──
    if name in ("/help", "/h", "/?"):
        _cmd_help()
    elif name in ("/new", "/newsession"):
        _cmd_new(state)
    elif name in ("/quit", "/q", "/exit"):
        _cmd_quit(state)

    # ── Info (local, no LLM) ──
    elif name in ("/cost", "/c"):
        _cmd_cost(state)
    elif name in ("/model", "/m"):
        _cmd_model(state, arg)
    elif name in ("/status",):
        _cmd_status(state)
    elif name in ("/memory", "/mem"):
        _cmd_memory()
    elif name in ("/soul",):
        _cmd_soul()
    elif name in ("/config",):
        _cmd_config(state)
    elif name in ("/sessions", "/s"):
        _cmd_sessions(arg)
    elif name in ("/search",):
        _cmd_search(arg)
    elif name in ("/recall",):
        _cmd_recall(arg, state)
    elif name in ("/skills",):
        _cmd_skills()
    elif name in ("/learnings",):
        _cmd_learnings(arg)
    elif name in ("/heartbeat",):
        _cmd_heartbeat()

    # ── Pipelines (LLM-backed) ──
    elif name in ("/produce",):
        _cmd_produce(state, arg)
    elif name in ("/evolve",):
        _cmd_evolve(state, arg)
    elif name in ("/learn",):
        _cmd_learn(state, arg)
    elif name in ("/absorb",):
        _cmd_absorb(state, arg)
    elif name in ("/reflect",):
        _cmd_reflect(state, arg)
    elif name in ("/digest",):
        _cmd_digest(arg)
    elif name in ("/gc",):
        _cmd_gc(arg)

    # ── Cron ──
    elif name in ("/loop",):
        _cmd_loop(arg)
    elif name in ("/loops",):
        _cmd_loops()
    elif name in ("/unloop",):
        _cmd_unloop(arg)
    elif name in ("/pause",):
        _cmd_toggle_job(arg, paused=True)
    elif name in ("/unpause",):
        _cmd_toggle_job(arg, paused=False)
    elif name in ("/notify",):
        _cmd_notify(arg)

    # ── Approval ──
    elif name in ("/queue",):
        _cmd_queue()
    elif name in ("/approve",):
        _cmd_approve(arg)
    elif name in ("/reject",):
        _cmd_reject(arg)

    # ── Admin ──
    elif name in ("/autonomy",):
        _cmd_autonomy(state, arg)

    else:
        console.print(f"[yellow]Unknown command: {name}[/yellow]")
        console.print("[dim]Type /help for available commands[/dim]")
    return True


# ══════════════════════════════════════════════════════════════════
#  LOCAL COMMANDS (no LLM call)
# ══════════════════════════════════════════════════════════════════

def _cmd_help():
    table = Table(
        show_header=False, box=None, padding=(0, 2, 0, 0),
        expand=True,
    )
    table.add_column("Command", style="cyan", no_wrap=True, min_width=22)
    table.add_column("Description", style="dim")

    # Session
    table.add_row("[bold white]SESSION[/bold white]", "")
    table.add_row("  /new", "Start a new conversation")
    table.add_row("  /quit", "Exit (also: Ctrl+D)")
    table.add_row("")

    # Pipelines
    table.add_row("[bold white]PIPELINES[/bold white]", "[dim italic]LLM-backed, takes 2-15 min[/dim italic]")
    table.add_row("  /produce [--ideas N]", "Brainstorm biz ideas from today's signals")
    table.add_row("  /evolve [--dry-run]", "Collect signals -> build -> install skills")
    table.add_row("  /learn <target>", "Deep-dive a repo, URL, or tech")
    table.add_row("  /absorb <target>", "Scan a repo and implement improvements")
    table.add_row("  /reflect [--days N]", "Self-analysis: patterns, gaps, next moves")
    table.add_row("  /digest [--days N]", "Morning briefing: sessions, signals, cost")
    table.add_row("  /gc [--dry-run]", "Clean stale sessions and orphan skills")
    table.add_row("")

    # Info
    table.add_row("[bold white]INFO[/bold white]", "")
    table.add_row("  /cost", "Spend breakdown (session / day / week)")
    table.add_row("  /model [name]", "Show or switch model")
    table.add_row("  /status", "System overview")
    table.add_row("  /memory", "Show MEMORY.md + USER.md")
    table.add_row("  /soul", "Show personality (SOUL.md)")
    table.add_row("  /config", "Show config.yaml")
    table.add_row("  /sessions [N]", "List recent sessions")
    table.add_row("  /search <query>", "FTS5 search past conversations")
    table.add_row("  /recall <query>", "Search all 6 memory layers")
    table.add_row("  /skills", "List installed skills")
    table.add_row("  /learnings [query]", "List or search past learnings")
    table.add_row("  /heartbeat", "Quick health check")
    table.add_row("")

    # Cron
    table.add_row("[bold white]CRON[/bold white]", "")
    table.add_row("  /loop <interval> <prompt>", "Create recurring job (e.g. 6h)")
    table.add_row("  /loops", "List all cron jobs")
    table.add_row("  /unloop <id>", "Delete a cron job")
    table.add_row("  /pause <id|--all>", "Pause a job")
    table.add_row("  /unpause <id|--all>", "Resume a job")
    table.add_row("  /notify <delay> <msg>", "One-shot reminder")
    table.add_row("")

    # Approval
    table.add_row("[bold white]APPROVAL[/bold white]", "")
    table.add_row("  /queue", "Skills pending review")
    table.add_row("  /approve <name>", "Install a queued skill")
    table.add_row("  /reject <name> [reason]", "Reject a queued skill")
    table.add_row("")

    # Admin
    table.add_row("[bold white]ADMIN[/bold white]", "")
    table.add_row("  /autonomy [level]", "Show or set (full/supervised/locked)")
    table.add_row("")

    # Voice (Telegram only)
    table.add_row("[bold white]VOICE[/bold white]", "[dim italic]Telegram only[/dim italic]")
    table.add_row("  /speak <text>", "Text-to-speech (auto-detects language)")
    table.add_row("  /speak --voices [lang]", "List available voices")
    table.add_row("  /speak --mode <off|always|inbound>", "Set auto-TTS mode")
    table.add_row("")

    # Platform digests (Telegram only)
    table.add_row("[bold white]PLATFORM DIGESTS[/bold white]", "[dim italic]Telegram only[/dim italic]")
    table.add_row("  /wechat [--hours N]", "WeChat group chat digest")
    table.add_row("  /discord [--hours N]", "Discord channel digest")
    table.add_row("  /whatsapp", "WhatsApp group digest")
    table.add_row("")

    # Monitoring (Telegram only)
    table.add_row("[bold white]MONITORING[/bold white]", "[dim italic]Telegram only[/dim italic]")
    table.add_row("  /subscribe", "Select channels to monitor for digests")
    table.add_row("  /serve", "Select channels/contacts for agent to respond in")
    table.add_row("")

    # Other (Telegram only)
    table.add_row("[bold white]OTHER[/bold white]", "[dim italic]Telegram only[/dim italic]")
    table.add_row("  /do <instruction>", "Natural language -> structured command")
    table.add_row("  /lang [code]", "Set output language (zh, en, ja, ko)")
    table.add_row("  /restart", "Restart gateway remotely")

    console.print()
    console.print(Panel(table, title="[bold]Commands[/bold]", border_style="blue", padding=(1, 2)))
    console.print("[dim]  Tab to autocomplete | Ctrl+C to interrupt | Ctrl+D to exit[/dim]")
    console.print()


def _cmd_new(state: SessionState):
    state.new_session()
    console.print("[green]New session started.[/green]")
    console.print(f"[dim]Session: {state.session_id}[/dim]")


def _cmd_quit(state: SessionState):
    state.end()
    console.print("[dim]Session ended. Goodbye.[/dim]")
    raise SystemExit(0)


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


def _cmd_status(state: SessionState):
    st = stats()
    today = get_today_cost()
    mem_path = EXODIR / "memory" / "MEMORY.md"
    user_path = EXODIR / "memory" / "USER.md"
    mem_chars = len(mem_path.read_text()) if mem_path.exists() else 0
    user_chars = len(user_path.read_text()) if user_path.exists() else 0
    skills_dir = Path.home() / ".claude" / "skills"
    skill_count = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.exists() else 0
    active_jobs = 0
    if CRON_JOBS_FILE.exists():
        try:
            jobs = json.loads(CRON_JOBS_FILE.read_text())
            active_jobs = sum(1 for j in jobs if not j.get("paused", False))
        except Exception:
            pass

    try:
        from gateway.autonomy import format_autonomy_status
        autonomy_info = format_autonomy_status(state.config)
    except Exception:
        autonomy_info = "unknown"

    table = Table(title="Status", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Session", state.session_id)
    table.add_row("Model", state.model)
    table.add_row("Messages", str(state.message_count))
    table.add_row("Session cost", f"${state.session_cost:.4f}")
    table.add_row("Today cost", f"${today:.4f}")
    table.add_row("Memory", f"{mem_chars}/2200 chars")
    table.add_row("User profile", f"{user_chars}/1375 chars")
    table.add_row("Skills", str(skill_count))
    table.add_row("Cron jobs", f"{active_jobs} active")
    table.add_row("Total sessions", str(st.get("total_sessions", 0)))
    table.add_row("Total messages", str(st.get("total_messages", 0)))
    table.add_row("DB size", f"{st.get('db_size_mb', 0)} MB")
    table.add_row("Autonomy", autonomy_info)
    console.print(table)


def _cmd_memory():
    for name, path, limit in [
        ("MEMORY.md", EXODIR / "memory" / "MEMORY.md", 2200),
        ("USER.md", EXODIR / "memory" / "USER.md", 1375),
    ]:
        if path.exists():
            content = path.read_text().strip()
            chars = len(content)
            pct = int(chars / limit * 100)
            console.print(Panel(
                Markdown(content),
                title=f"{name} [{pct}% — {chars}/{limit} chars]",
                border_style="cyan",
            ))
        else:
            console.print(f"[dim]{name} not found.[/dim]")


def _cmd_soul():
    soul_path = EXODIR / "SOUL.md"
    if soul_path.exists():
        console.print(Panel(Markdown(soul_path.read_text().strip()), title="SOUL.md", border_style="magenta"))
    else:
        console.print("[dim]SOUL.md not found.[/dim]")


def _cmd_config(state: SessionState):
    cfg = state.config
    try:
        from gateway.autonomy import format_autonomy_status
        autonomy = format_autonomy_status(cfg)
    except Exception:
        autonomy = "unknown"

    table = Table(title="Config", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("model", cfg.get("model", "sonnet"))
    table.add_row("daily_cost_cap", str(cfg.get("daily_cost_cap", 5.0)))
    table.add_row("weekly_cost_cap", str(cfg.get("weekly_cost_cap", 25.0)))
    table.add_row("session_idle_minutes", str(cfg.get("session_idle_minutes", 120)))
    table.add_row("autonomy", autonomy)
    platforms = cfg.get("platforms", {})
    for p_name, p_cfg in platforms.items():
        enabled = p_cfg.get("enabled", True)
        table.add_row(f"platform.{p_name}", "enabled" if enabled else "disabled")
    console.print(table)


def _cmd_sessions(arg: str):
    limit = int(arg) if arg and arg.isdigit() else 10
    sessions = list_sessions(limit=limit)
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return
    table = Table(title="Recent Sessions", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", max_width=25)
    table.add_column("Source", max_width=10)
    table.add_column("Title", max_width=40)
    table.add_column("Msgs", justify="right")
    table.add_column("Started", max_width=16)
    for s in sessions:
        started = s.get("started_at", "")[:16] if s.get("started_at") else "-"
        table.add_row(
            s.get("id", ""), s.get("source", ""),
            (s.get("title") or "-")[:40], str(s.get("message_count", 0)), started,
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


def _cmd_recall(arg: str, state: SessionState):
    if not arg:
        console.print("[yellow]Usage: /recall <query>[/yellow]")
        return
    results = unified_search(arg, session_id=state.session_id, limit_per_layer=5)
    formatted = format_recall_context(results, max_chars=3800)
    if formatted:
        console.print(Markdown(formatted))
    else:
        console.print("[dim]No results found across memory layers.[/dim]")


def _cmd_skills():
    skills_dir = Path.home() / ".claude" / "skills"
    if not skills_dir.exists():
        console.print("[dim]No skills directory found.[/dim]")
        return
    skills = sorted(skills_dir.glob("*/SKILL.md"))
    if not skills:
        console.print("[dim]No skills installed.[/dim]")
        return
    table = Table(title=f"Installed Skills ({len(skills)})", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Description", max_width=50)
    for sp in skills:
        name = sp.parent.name
        # Extract first non-empty, non-heading line as description
        desc = ""
        for line in sp.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                desc = line[:50]
                break
        table.add_row(name, desc)
    console.print(table)

    # Check queue
    queue_dir = EXODIR / "skills-queue"
    if queue_dir.exists():
        queued = list(queue_dir.glob("*/SKILL.md"))
        if queued:
            console.print(f"[yellow]{len(queued)} skills pending in queue. Use /queue to review.[/yellow]")


def _cmd_learnings(arg: str):
    try:
        from gateway.session_db import list_learnings, search_learnings
    except ImportError:
        console.print("[red]learnings not available[/red]")
        return

    if arg:
        items = search_learnings(arg, limit=10)
    else:
        items = list_learnings(limit=10)

    if not items:
        console.print("[dim]No learnings found.[/dim]")
        return

    table = Table(title="Learnings", show_header=True, header_style="bold")
    table.add_column("Verdict", style="cyan", max_width=8)
    table.add_column("Target", max_width=35)
    table.add_column("Patterns", max_width=40)
    table.add_column("Skill", max_width=15)
    table.add_column("Date", max_width=10)
    for item in items:
        table.add_row(
            item.get("verdict", "?"),
            (item.get("target", ""))[:35],
            (item.get("patterns", ""))[:40],
            item.get("skill_created", "") or "-",
            (item.get("created_at", ""))[:10],
        )
    console.print(table)


def _cmd_heartbeat():
    today = get_today_cost()
    console.print(f"PID: {os.getpid()}")
    console.print(f"Cost today: ${today:.4f}")
    console.print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")


# ══════════════════════════════════════════════════════════════════
#  PIPELINE COMMANDS (LLM-backed)
# ══════════════════════════════════════════════════════════════════

def _cmd_produce(state: SessionState, arg: str):
    """Aggregate signals and brainstorm business ideas."""
    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--model": {"type": "value"},
        "--ideas": {"type": "value", "cast": int, "default": 5},
    })
    num_ideas = max(1, min(flags["--ideas"], 10))
    model = flags["--model"] or state.model

    console.print(f"[dim]Aggregating signals, brainstorming {num_ideas} ideas...[/dim]")

    # Import and call _build_produce's logic inline (it's an instance method on SignalsMixin,
    # but its core logic is just file reads + invoke_claude_streaming)
    signals_dir = EXODIR / "signals"
    today = datetime.now().strftime("%Y-%m-%d")
    today_dir = signals_dir / today

    all_signals = []
    source_counts = {}
    if today_dir.exists():
        for f in sorted(today_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                sigs = data if isinstance(data, list) else [data]
                source_counts[f.stem] = len(sigs)
                all_signals.extend(sigs)
            except Exception:
                continue

    if not all_signals:
        console.print("[yellow]No signals found for today. Run /evolve first to collect signals.[/yellow]")
        return

    console.print(f"[dim]Loaded {len(all_signals)} signals from {len(source_counts)} sources[/dim]")

    # Build condensed signal summary
    source_summaries = []
    for source_name, count in sorted(source_counts.items()):
        source_signals = [s for s in all_signals
                          if s.get("source", "") == source_name.replace("-", "")
                          or s.get("source", "") == source_name
                          or s.get("id", "").startswith(source_name.split("-")[0])]
        source_signals.sort(
            key=lambda x: (x.get("metadata", {}).get("points", 0) or x.get("metadata", {}).get("stars", 0) or 0),
            reverse=True
        )
        items = []
        for s in source_signals[:8]:
            title = s.get("title", "")
            content = s.get("content", "")[:200]
            url = s.get("url", "")
            engagement = s.get("metadata", {}).get("points", 0) or s.get("metadata", {}).get("stars", 0) or 0
            items.append(f"  - {title} ({engagement} pts) {url}\n    {content}")
        if items:
            source_summaries.append(f"### {source_name} ({count} signals)\n" + "\n".join(items))

    signals_text = "\n\n".join(source_summaries)
    if len(signals_text) > 40000:
        signals_text = signals_text[:40000] + "\n\n... (truncated)"

    prompt = (
        f"You are Vincent's personal AI business strategist.\n\n"
        f"Vincent builds AI agents, onchain infrastructure, and developer tools.\n\n"
        f"Here are the latest signals from {len(source_counts)} sources ({len(all_signals)} total):\n\n"
        f"{signals_text}\n\n"
        f"Generate exactly {num_ideas} concrete business/app ideas. "
        f"For each: one-liner, why now, target users, revenue model, tech stack, MVP scope, "
        f"competitive moat, estimated effort, revenue potential.\n"
        f"Rank by feasibility x market timing x revenue potential. Use Markdown."
    )

    result = _invoke_claude_streaming(
        prompt, on_progress=_cli_progress, model=model,
        session_context=f"[Produce: {num_ideas} ideas from {len(all_signals)} signals]"
    )

    text = result.get("text", "No ideas generated.")
    cost = result.get("cost", 0.0)
    sources_line = ", ".join(f"{k}({v})" for k, v in sorted(source_counts.items()))
    console.print()
    console.print(Markdown(f"**Business Ideas** — {len(all_signals)} signals\nSources: {sources_line}\n\n{text}"))
    console.print(f"\n[dim]${cost:.4f}[/dim]")
    if cost > 0:
        log_cost(cost, platform="cli", session_id=state.session_id, pipeline="produce")


def _cmd_evolve(state: SessionState, arg: str):
    """Run the multi-stage evolve pipeline."""
    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
        "--skip-security-scan": {"type": "bool"},
        "--model": {"type": "value"},
    })
    dry_run = flags["--dry-run"]
    model = flags["--model"] or state.model

    stages = "COLLECT -> ANALYZE" if dry_run else "COLLECT -> ANALYZE -> BUILD -> REVIEW -> REPORT"
    console.print(f"[dim]Evolving... {stages}[/dim]")
    console.print(f"[dim]~{'2-4' if dry_run else '5-10'} min[/dim]")

    from gateway.evolve import EvolveOrchestrator
    orchestrator = EvolveOrchestrator(
        model=model, on_progress=_cli_progress,
        skip_security_scan=flags["--skip-security-scan"],
    )

    try:
        summary, cost = orchestrator.run(dry_run=dry_run)
    except Exception as e:
        console.print(f"[red]Evolve failed: {e}[/red]")
        return

    console.print()
    console.print(Markdown(summary))
    console.print(f"\n[dim]${cost:.4f}[/dim]")
    if cost > 0:
        log_cost(cost, platform="cli", session_id=state.session_id, pipeline="evolve")


def _cmd_learn(state: SessionState, arg: str):
    """Deep-dive a repo, URL, or tech."""
    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--skip-security-scan": {"type": "bool"},
        "--model": {"type": "value"},
        "--dry-run": {"aliases": ["dry-run", "preview"], "type": "bool"},
    })
    target = " ".join(raw_args).strip()
    if not target:
        console.print("[yellow]Usage: /learn <repo-url or tech name>[/yellow]")
        console.print("[dim]  --dry-run    Preview only[/dim]")
        console.print("[dim]  --model X    Override model[/dim]")
        return

    model = flags["--model"] or state.model
    is_url = target.startswith("http://") or target.startswith("https://")
    is_github = "github.com" in target

    if flags["--dry-run"]:
        console.print(f"[dim]Learn dry run: {target}[/dim]")
        console.print(f"  Type: {'GitHub' if is_github else 'URL' if is_url else 'topic'}")
        console.print(f"  Model: {model}")
        return

    console.print(f"[dim]Learning: {target[:60]}...[/dim]")
    console.print(f"[dim]~3-6 min[/dim]")

    system_context = (
        "You are the LEARN agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
        "Our system: Python asyncio gateway -> Claude Code (claude -p). "
        "Bounded memory (MEMORY.md/USER.md), SQLite+FTS5, agent-managed cron, skills in ~/.claude/skills/.\n\n"
        "Vincent builds AI agents, onchain infrastructure, and developer tools.\n\n"
    )
    analysis = (
        "EXTRACT PATTERNS: design patterns, architectural decisions, stealable techniques.\n"
        "EVALUATE: ADOPT / STEAL / SKIP verdict. If ADOPT or STEAL, create a skill in ~/.claude/skills/<name>/SKILL.md.\n"
        "Update MEMORY.md with findings.\n"
        "Return: patterns, verdict, skill/memory updates.\n"
    )

    if is_github:
        prompt = system_context + f"Deep-dive this GitHub repo: {target}\n\n" + analysis
    elif is_url:
        prompt = system_context + f"Research this URL: {target}\n\n" + analysis
    else:
        prompt = system_context + f"Research this technology: {target}\n\n" + analysis

    result = _invoke_claude_streaming(
        prompt, on_progress=_cli_progress, model=model,
        session_context=f"[Learn: {target[:50]}]"
    )

    text = result.get("text", "No output.")
    cost = result.get("cost", 0.0)
    console.print()
    console.print(Markdown(text))
    console.print(f"\n[dim]${cost:.4f}[/dim]")
    if cost > 0:
        log_cost(cost, platform="cli", session_id=state.session_id, pipeline="learn")

    # Store learning
    try:
        from gateway.session_db import add_learning
        target_type = "github" if is_github else ("url" if is_url else "topic")
        learning_data = {"verdict": "UNKNOWN", "patterns": "", "operational_benefit": "", "skill_created": ""}
        json_start = text.rfind('```json')
        json_end = text.rfind('```', json_start + 7) if json_start >= 0 else -1
        if json_start >= 0 and json_end > json_start:
            try:
                learning_data = json.loads(text[json_start + 7:json_end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        add_learning(
            target=target, target_type=target_type,
            verdict=learning_data.get("verdict", "UNKNOWN"),
            patterns=learning_data.get("patterns", ""),
            operational_benefit=learning_data.get("operational_benefit", ""),
            skill_created=learning_data.get("skill_created", ""),
            full_report=text[:8000], cost=cost,
        )
    except Exception:
        pass


def _cmd_absorb(state: SessionState, arg: str):
    """Scan + implement improvements from a target."""
    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
        "--skip-security-scan": {"type": "bool"},
        "--model": {"type": "value"},
    })
    target = " ".join(raw_args).strip()
    if not target:
        console.print("[yellow]Usage: /absorb <repo-url or tech>[/yellow]")
        return

    model = flags["--model"] or state.model
    is_github = "github.com" in target
    is_url = target.startswith("http://") or target.startswith("https://")
    target_type = "github" if is_github else ("url" if is_url else "topic")

    stages = "SCAN -> GAP" if flags["--dry-run"] else "SCAN -> GAP -> PLAN -> IMPLEMENT -> REPORT"
    console.print(f"[dim]Absorbing: {target[:60]}[/dim]")
    console.print(f"[dim]{stages} | ~{'3-5' if flags['--dry-run'] else '8-15'} min[/dim]")

    from gateway.absorb import AbsorbOrchestrator
    orchestrator = AbsorbOrchestrator(
        target=target, target_type=target_type, model=model,
        on_progress=_cli_progress, skip_security_scan=flags["--skip-security-scan"],
    )

    try:
        summary, cost = orchestrator.run(dry_run=flags["--dry-run"])
    except Exception as e:
        console.print(f"[red]Absorb failed: {e}[/red]")
        return

    console.print()
    console.print(Markdown(summary))
    console.print(f"\n[dim]${cost:.4f}[/dim]")
    if cost > 0:
        log_cost(cost, platform="cli", session_id=state.session_id, pipeline="absorb")

    try:
        from gateway.session_db import add_learning
        add_learning(
            target=target, target_type=target_type, verdict="ABSORBED",
            patterns="Absorbed via 5-stage pipeline.",
            operational_benefit=f"Cost: ${cost:.2f}",
            skill_created="", full_report=summary[:8000], cost=cost,
        )
    except Exception:
        pass


def _cmd_reflect(state: SessionState, arg: str):
    """Self-analysis: patterns, avoidance, next actions."""
    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--days": {"type": "value", "cast": int, "default": 7},
        "--model": {"type": "value"},
    })
    days = max(1, min(flags["--days"], 30))
    model = flags["--model"] or state.model

    console.print(f"[dim]Reflecting on the last {days} days... ~2-4 min[/dim]")

    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()

    prompt = (
        f"You are the REFLECT agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
        f"Run a {days}-day self-analysis:\n\n"
        f"1. Query SQLite DB at {EXODIR}/memory/sessions.db for sessions since {since}\n"
        f"2. Check git log in ~/Desktop/projects/agenticEvolve since {since[:10]}\n"
        f"3. List skills in ~/.claude/skills/\n"
        f"4. Read MEMORY.md and USER.md\n"
        f"5. Return: patterns, avoidance, 3 things to build next, system health\n\n"
        f"Be concise and actionable. No filler."
    )

    result = _invoke_claude_streaming(
        prompt, on_progress=_cli_progress, model=model,
        session_context="[Reflect pipeline]"
    )

    text = result.get("text", "No output.")
    cost = result.get("cost", 0.0)
    console.print()
    console.print(Markdown(f"**Reflect — last {days}d**\n\n{text}"))
    console.print(f"\n[dim]${cost:.4f}[/dim]")
    if cost > 0:
        log_cost(cost, platform="cli", session_id=state.session_id, pipeline="reflect")


def _cmd_digest(arg: str):
    """Morning briefing: sessions, signals, cost."""
    import sqlite3
    from gateway.session_db import DB_PATH

    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--days": {"type": "value", "cast": int, "default": 1},
    })
    days = max(1, min(flags["--days"], 7))

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    since_str = since.isoformat()

    # Sessions
    sessions_summary = ""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, message_count, source, started_at FROM sessions "
            "WHERE started_at >= ? ORDER BY started_at DESC LIMIT 20",
            (since_str,)
        ).fetchall()
        conn.close()
        if rows:
            lines = [f"  {r['started_at'][:16]} — {(r['title'] or '(untitled)')[:50]} ({r['message_count']} msgs)" for r in rows]
            sessions_summary = "\n".join(lines)
        else:
            sessions_summary = "  (none)"
    except Exception:
        sessions_summary = "  (error)"

    # Signals
    signals_summary = ""
    try:
        sig_dir = EXODIR / "signals" / now.strftime("%Y-%m-%d")
        if not sig_dir.exists():
            sig_dirs = sorted((EXODIR / "signals").glob("????-??-??")) if (EXODIR / "signals").exists() else []
            sig_dir = sig_dirs[-1] if sig_dirs else None
        if sig_dir and sig_dir.exists():
            signal_lines = []
            for f in sorted(sig_dir.glob("*.json"))[:3]:
                try:
                    for line in f.read_text().splitlines()[:5]:
                        if not line.strip():
                            continue
                        obj = json.loads(line)
                        title = obj.get("title", obj.get("name", ""))[:60]
                        if title:
                            signal_lines.append(f"  [{f.stem}] {title}")
                except Exception:
                    pass
            signals_summary = "\n".join(signal_lines[:5]) if signal_lines else "  (none)"
        else:
            signals_summary = "  (no signals)"
    except Exception:
        signals_summary = "  (error)"

    # Skills
    skills_built = ""
    try:
        skills_dir = Path.home() / ".claude" / "skills"
        if skills_dir.exists():
            new_skills = [sp.parent.name for sp in skills_dir.glob("*/SKILL.md")
                          if datetime.fromtimestamp(sp.stat().st_mtime, tz=timezone.utc) >= since]
            skills_built = "\n".join(f"  {s}" for s in new_skills) if new_skills else "  (none)"
        else:
            skills_built = "  (none)"
    except Exception:
        skills_built = "  (error)"

    cost_today = get_today_cost()

    # Cron
    cron_summary = ""
    try:
        if CRON_JOBS_FILE.exists():
            jobs = json.loads(CRON_JOBS_FILE.read_text())
            active = [j for j in jobs if not j.get("paused")]
            lines = [f"  {j.get('id', '?')} -> {j.get('next_run_at', '?')[:16]}" for j in active[:5]]
            cron_summary = "\n".join(lines) if lines else "  (none active)"
        else:
            cron_summary = "  (no jobs)"
    except Exception:
        cron_summary = "  (error)"

    period = "today" if days == 1 else f"last {days}d"
    text = (
        f"**Digest — {now.strftime('%Y-%m-%d %H:%M')} UTC**\n\n"
        f"**Sessions ({period}):**\n{sessions_summary}\n\n"
        f"**Top signals:**\n{signals_summary}\n\n"
        f"**Skills built ({period}):**\n{skills_built}\n\n"
        f"**Cost today:** ${cost_today:.2f}\n\n"
        f"**Cron (next runs):**\n{cron_summary}"
    )
    console.print(Markdown(text))


def _cmd_gc(arg: str):
    """Run garbage collection."""
    raw_args = arg.split() if arg else []
    flags = _parse_flags(raw_args, {
        "--dry-run": {"aliases": ["dry-run", "dry", "preview"], "type": "bool"},
    })

    from gateway.gc import run_gc, format_gc_report
    console.print(f"[dim]Running GC{' (dry run)' if flags['--dry-run'] else ''}...[/dim]")
    report = run_gc(dry_run=flags["--dry-run"])
    text = format_gc_report(report)
    console.print(Markdown(text))


# ══════════════════════════════════════════════════════════════════
#  CRON COMMANDS
# ══════════════════════════════════════════════════════════════════

def _load_cron_jobs() -> list[dict]:
    if CRON_JOBS_FILE.exists():
        try:
            return json.loads(CRON_JOBS_FILE.read_text())
        except Exception:
            return []
    return []


def _save_cron_jobs(jobs: list[dict]):
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    CRON_JOBS_FILE.write_text(json.dumps(jobs, indent=2))


def _parse_interval(s: str) -> int | None:
    """Parse interval string like '5m', '2h', '1d' to seconds."""
    import re
    m = re.match(r'^(\d+)\s*(s|sec|m|min|h|hr|hour|d|day)s?$', s.lower())
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit in ('s', 'sec'):
        return n
    if unit in ('m', 'min'):
        return n * 60
    if unit in ('h', 'hr', 'hour'):
        return n * 3600
    if unit in ('d', 'day'):
        return n * 86400
    return None


def _cmd_loop(arg: str):
    """Create a recurring cron job."""
    if not arg:
        console.print("[yellow]Usage: /loop <interval> <prompt>[/yellow]")
        console.print("[dim]  e.g. /loop 6h check for new AI papers and summarize[/dim]")
        return

    parts = arg.split(None, 1)
    if len(parts) < 2:
        console.print("[yellow]Need both interval and prompt[/yellow]")
        return

    interval = _parse_interval(parts[0])
    if not interval:
        console.print(f"[yellow]Invalid interval: {parts[0]}[/yellow]")
        console.print("[dim]  Examples: 5m, 2h, 1d[/dim]")
        return

    prompt = parts[1]
    job_id = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    job = {
        "id": job_id,
        "prompt": prompt,
        "schedule_type": "interval",
        "interval_seconds": interval,
        "deliver_to": "cli",
        "deliver_chat_id": "",
        "created_at": now.isoformat(),
        "next_run_at": (now + timedelta(seconds=interval)).isoformat(),
        "run_count": 0,
        "paused": False,
    }
    jobs = _load_cron_jobs()
    jobs.append(job)
    _save_cron_jobs(jobs)
    console.print(f"[green]Created loop {job_id}: every {parts[0]}[/green]")
    console.print(f"[dim]Prompt: {prompt[:60]}...[/dim]")


def _cmd_loops():
    """List active cron jobs."""
    jobs = _load_cron_jobs()
    if not jobs:
        console.print("[dim]No cron jobs.[/dim]")
        return
    table = Table(title="Cron Jobs", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Interval")
    table.add_column("Runs", justify="right")
    table.add_column("Next Run", max_width=16)
    table.add_column("Prompt", max_width=30)
    for j in jobs:
        status = "[red]paused[/red]" if j.get("paused") else "[green]active[/green]"
        secs = j.get("interval_seconds", 0)
        if secs >= 86400:
            interval = f"{secs // 86400}d"
        elif secs >= 3600:
            interval = f"{secs // 3600}h"
        elif secs >= 60:
            interval = f"{secs // 60}m"
        else:
            interval = f"{secs}s"
        table.add_row(
            j.get("id", "?"), status, interval,
            str(j.get("run_count", 0)),
            j.get("next_run_at", "?")[:16],
            (j.get("prompt", ""))[:30],
        )
    console.print(table)


def _cmd_unloop(arg: str):
    """Remove a cron job."""
    if not arg:
        console.print("[yellow]Usage: /unloop <id>[/yellow]")
        return
    job_id = arg.strip()
    jobs = _load_cron_jobs()
    new_jobs = [j for j in jobs if j.get("id") != job_id]
    if len(new_jobs) == len(jobs):
        console.print(f"[yellow]Job {job_id} not found[/yellow]")
        return
    _save_cron_jobs(new_jobs)
    console.print(f"[green]Removed job {job_id}[/green]")


def _cmd_toggle_job(arg: str, paused: bool):
    """Pause or unpause a cron job."""
    if not arg:
        console.print(f"[yellow]Usage: /{'pause' if paused else 'unpause'} <id|--all>[/yellow]")
        return
    jobs = _load_cron_jobs()
    if arg.strip() == "--all":
        for j in jobs:
            j["paused"] = paused
        _save_cron_jobs(jobs)
        console.print(f"[green]All jobs {'paused' if paused else 'unpaused'}[/green]")
        return
    job_id = arg.strip()
    found = False
    for j in jobs:
        if j.get("id") == job_id:
            j["paused"] = paused
            found = True
    if not found:
        console.print(f"[yellow]Job {job_id} not found[/yellow]")
        return
    _save_cron_jobs(jobs)
    console.print(f"[green]Job {job_id} {'paused' if paused else 'unpaused'}[/green]")


def _cmd_notify(arg: str):
    """One-shot delayed notification."""
    if not arg:
        console.print("[yellow]Usage: /notify <delay> <message>[/yellow]")
        console.print("[dim]  e.g. /notify 30m check deployment status[/dim]")
        return
    parts = arg.split(None, 1)
    if len(parts) < 2:
        console.print("[yellow]Need both delay and message[/yellow]")
        return
    delay = _parse_interval(parts[0])
    if not delay:
        console.print(f"[yellow]Invalid delay: {parts[0]}[/yellow]")
        return
    msg = parts[1]
    job_id = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    job = {
        "id": job_id,
        "prompt": msg,
        "schedule_type": "once",
        "interval_seconds": 0,
        "deliver_to": "cli",
        "deliver_chat_id": "",
        "created_at": now.isoformat(),
        "next_run_at": (now + timedelta(seconds=delay)).isoformat(),
        "run_count": 0,
        "max_runs": 1,
        "paused": False,
    }
    jobs = _load_cron_jobs()
    jobs.append(job)
    _save_cron_jobs(jobs)
    console.print(f"[green]Notification scheduled in {parts[0]}: {msg[:60]}[/green]")


# ══════════════════════════════════════════════════════════════════
#  APPROVAL COMMANDS
# ══════════════════════════════════════════════════════════════════

def _cmd_queue():
    try:
        from gateway.evolve import list_queue
    except ImportError:
        console.print("[red]evolve module not available[/red]")
        return
    items = list_queue()
    if not items:
        console.print("[dim]No skills in queue.[/dim]")
        return
    for item in items:
        console.print(f"[cyan]{item.get('name', '?')}[/cyan]")
        if item.get("review", {}).get("issues"):
            for issue in item["review"]["issues"]:
                console.print(f"  [yellow]{issue}[/yellow]")


def _cmd_approve(arg: str):
    if not arg:
        console.print("[yellow]Usage: /approve <skill-name> [--force][/yellow]")
        return
    parts = arg.split()
    name = parts[0]
    force = "--force" in parts or "-f" in parts
    try:
        from gateway.evolve import approve_skill, approve_skill_force
        ok, msg = approve_skill_force(name) if force else approve_skill(name)
        style = "green" if ok else "red"
        console.print(f"[{style}]{msg}[/{style}]")
    except ImportError:
        console.print("[red]evolve module not available[/red]")


def _cmd_reject(arg: str):
    if not arg:
        console.print("[yellow]Usage: /reject <skill-name> [reason][/yellow]")
        return
    parts = arg.split(None, 1)
    name = parts[0]
    reason = parts[1] if len(parts) > 1 else "Rejected via CLI"
    try:
        from gateway.evolve import reject_skill
        ok, msg = reject_skill(name, reason)
        style = "green" if ok else "red"
        console.print(f"[{style}]{msg}[/{style}]")
    except ImportError:
        console.print("[red]evolve module not available[/red]")


# ══════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════

def _cmd_autonomy(state: SessionState, arg: str):
    """Show or set autonomy level."""
    try:
        from gateway.autonomy import format_autonomy_status
    except ImportError:
        console.print("[red]autonomy module not available[/red]")
        return

    if not arg:
        console.print(format_autonomy_status(state.config))
        console.print("[dim]Usage: /autonomy <full|supervised|locked>[/dim]")
        return

    level = arg.strip().lower()
    if level not in ("full", "supervised", "locked"):
        console.print(f"[yellow]Invalid level: {level}. Use full, supervised, or locked.[/yellow]")
        return

    try:
        import yaml
        config_path = CONFIG_PATH
        raw = yaml.safe_load(config_path.read_text()) or {}
        raw["autonomy"] = level
        config_path.write_text(yaml.dump(raw, default_flow_style=False))
        state.config["autonomy"] = level
        console.print(f"[green]Autonomy set to: {level}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to update config: {e}[/red]")


# ── Cost Cap Check ──────────────────────────────────────────────

def check_cost_cap(config: dict) -> str | None:
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
    """Entry point for ae."""
    config = load_config()
    state = SessionState(config)

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

    history_file = EXODIR / ".cli_history"
    prompt_session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=SlashCompleter(),
        complete_while_typing=True,
    )

    while True:
        try:
            user_input = prompt_session.prompt("you> ", multiline=False).strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                handle_command(user_input, state)
                continue

            cap_msg = check_cost_cap(config)
            if cap_msg:
                console.print(f"[red]{cap_msg}[/red]")
                continue

            state.add_user_message(user_input)
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
            state.end()
            console.print("\n[dim]Session ended. Goodbye.[/dim]")
            break


if __name__ == "__main__":
    main()
