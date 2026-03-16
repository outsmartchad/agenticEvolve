"""
ae — agenticEvolve TUI (Textual-based).

Full-screen terminal UI with:
- Split-pane layout (messages + sidebar)
- Real-time streaming with per-token updates
- Tool execution panels (file read/edit/bash with context)
- Side-by-side diff rendering for edits
- Status bar with model, cost, tokens, keybindings
- Overlay dialogs (help, session picker, model switcher)
- All 42 slash commands with autocomplete
"""

from __future__ import annotations

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
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    RichLog,
    Static,
    TextArea,
)

from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text

# ── Bootstrap ───────────────────────────────────────────────────

EXODIR = Path.home() / ".agenticEvolve"
sys.path.insert(0, str(EXODIR))

from gateway.config import load_config
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
    get_user_pref,
    set_user_pref,
    delete_user_pref,
    get_subscriptions,
    add_subscription,
    remove_subscription,
    get_serve_targets,
)

# ── Language codes ──────────────────────────────────────────────

LANG_NAMES = {
    "zh": "Simplified Chinese (简体中文)",
    "zh-tw": "Traditional Chinese (繁體中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
}

# ── Intent parser schema (for /do) ─────────────────────────────

_COMMAND_SCHEMA = """Available commands:
/absorb <repo-url or topic> [--dry-run] [--model <name>] [--skip-security-scan]
/learn <repo-url or topic> [--dry-run] [--model <name>] [--skip-security-scan]
/evolve [--dry-run] [--model <name>] [--skip-security-scan]
/search <query> [--limit <n>]
/sessions [--limit <n>]
/new [title]
/memory
/cost [--week]
/status
/skills
/learnings [query] [--limit <n>]
/model <name>
/produce [--ideas N] [--model <name>]
/wechat [--hours N] [--model <name>]
/digest [--days N]
/gc [--dry-run]
/loop <interval> <prompt> [--model <name>] [--max-runs <n>] [--start-now]
/loops
/unloop <id>
/pause <id|--all>
/unpause <id|--all>
/queue
/approve <name> [--force]
/reject <name>
/soul
/config
/heartbeat
/notify <duration> <message>
/help
"""

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


# ── Custom Messages ─────────────────────────────────────────────

class StreamToken(Message):
    """A token of text streamed from Claude."""
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class ToolStart(Message):
    """Claude started using a tool."""
    def __init__(self, name: str, input_data: dict) -> None:
        super().__init__()
        self.name = name
        self.input_data = input_data


class ToolEnd(Message):
    """Tool execution completed."""
    def __init__(self) -> None:
        super().__init__()


class StreamDone(Message):
    """Streaming completed."""
    def __init__(self, text: str, cost: float, success: bool) -> None:
        super().__init__()
        self.text = text
        self.cost = cost
        self.success = success


class CommandOutput(Message):
    """Output from a slash command."""
    def __init__(self, content: str, is_markdown: bool = False) -> None:
        super().__init__()
        self.content = content
        self.is_markdown = is_markdown


# ── Tool Description ────────────────────────────────────────────

def _tool_description(name: str, input_data: dict) -> str:
    """One-liner description of a tool call."""
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
        return f"$ {cmd[:60]}" if cmd else "Running command"
    if name in ("Glob", "Search"):
        pattern = input_data.get("pattern", "")
        return f"Finding: {pattern}" if pattern else "Searching files"
    if name == "Grep":
        pattern = input_data.get("pattern", "")
        return f"Grep: {pattern[:40]}" if pattern else "Searching content"
    if name == "WebFetch":
        url = input_data.get("url", "")
        return f"Fetching: {url[:50]}" if url else "Fetching URL"
    if name == "Task":
        desc = input_data.get("description", "")
        return f"Agent: {desc}" if desc else "Sub-agent"
    if name == "TodoWrite":
        return "Updating task list"
    return f"Using {name}"


def _tool_icon(name: str) -> str:
    """Icon for a tool type."""
    icons = {
        "Read": "📖", "Write": "📝", "Edit": "✏️",
        "Bash": "💻", "Glob": "🔍", "Grep": "🔎",
        "WebFetch": "🌐", "Task": "🤖", "TodoWrite": "📋",
        "Search": "🔍",
    }
    return icons.get(name, "🔧")


# ── Widgets ─────────────────────────────────────────────────────

class UserMessage(Static):
    """A user message bubble."""
    DEFAULT_CSS = """
    UserMessage {
        margin: 0 1 0 1;
        padding: 0 1;
        background: $primary-background;
        border-left: thick $secondary;
        color: $text;
    }
    """


class AssistantMessage(Widget):
    """An assistant message rendered as Markdown."""
    DEFAULT_CSS = """
    AssistantMessage {
        margin: 0 1 0 1;
        padding: 0 1;
        border-left: thick $primary;
        height: auto;
    }
    AssistantMessage Markdown {
        margin: 0;
        padding: 0;
    }
    """

    def __init__(self, content: str = "") -> None:
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        yield Markdown(self._content)

    def update_content(self, content: str) -> None:
        self._content = content
        try:
            md = self.query_one(Markdown)
            md.update(content)
        except NoMatches:
            pass


class ToolPanel(Static):
    """Shows a tool execution with icon, description, and optional details."""
    DEFAULT_CSS = """
    ToolPanel {
        margin: 0 1 0 2;
        padding: 0 1;
        border-left: thick $warning;
        color: $text-muted;
        height: auto;
    }
    """

    def __init__(self, name: str, input_data: dict, active: bool = True) -> None:
        icon = _tool_icon(name)
        desc = _tool_description(name, input_data)
        dots = " ..." if active else ""
        # Show file path context for file operations
        fp = input_data.get("file_path") or input_data.get("filePath", "")
        extra = ""
        if name == "Edit" and fp:
            old = input_data.get("old_string") or input_data.get("oldString", "")
            if old:
                preview = old.strip()[:80].replace("\n", "\\n")
                extra = f"\n  [dim]{fp}[/dim]\n  [dim red]-{preview}[/dim red]"
        elif name == "Bash":
            cmd = input_data.get("command", "")
            if cmd and len(cmd) > 60:
                extra = f"\n  [dim]{cmd[:120]}[/dim]"
        elif name == "Read" and fp:
            extra = f"\n  [dim]{fp}[/dim]"
        elif name == "Write" and fp:
            extra = f"\n  [dim]{fp}[/dim]"
        elif name == "Task":
            prompt = input_data.get("prompt", "")
            if prompt:
                extra = f"\n  [dim]{prompt[:100]}[/dim]"

        markup = f"{icon} {desc}{dots}{extra}"
        super().__init__(markup)


class Sidebar(Widget):
    """Right sidebar showing session info and modified files."""
    DEFAULT_CSS = """
    Sidebar {
        width: 30;
        height: 100%;
        padding: 1 1;
        border-left: tall $surface;
        background: $surface;
    }
    Sidebar .sidebar-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    Sidebar .sidebar-label {
        color: $text-muted;
    }
    Sidebar .sidebar-value {
        color: $text;
        margin-bottom: 1;
    }
    """

    def __init__(self, state: SessionState) -> None:
        super().__init__()
        self.state = state
        self._files_changed: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("agenticEvolve", classes="sidebar-header")
        yield Static("", id="sidebar-session", classes="sidebar-label")
        yield Static("", id="sidebar-model", classes="sidebar-label")
        yield Static("", id="sidebar-cost", classes="sidebar-label")
        yield Static("", id="sidebar-msgs", classes="sidebar-label")
        yield Static("", id="sidebar-files-header", classes="sidebar-header")
        yield Static("", id="sidebar-files", classes="sidebar-value")

    def refresh_info(self) -> None:
        try:
            self.query_one("#sidebar-session", Static).update(
                f"Session: {self.state.session_id[:16]}..."
            )
            self.query_one("#sidebar-model", Static).update(
                f"Model: {self.state.model}"
            )
            self.query_one("#sidebar-cost", Static).update(
                f"Cost: ${self.state.session_cost:.4f}"
            )
            self.query_one("#sidebar-msgs", Static).update(
                f"Messages: {self.state.message_count}"
            )
        except NoMatches:
            pass

    def update_files(self, files: list[str]) -> None:
        self._files_changed = files
        try:
            if files:
                self.query_one("#sidebar-files-header", Static).update("Modified Files")
                lines = "\n".join(f"  {Path(f).name}" for f in files[-10:])
                self.query_one("#sidebar-files", Static).update(lines)
            else:
                self.query_one("#sidebar-files-header", Static).update("")
                self.query_one("#sidebar-files", Static).update("")
        except NoMatches:
            pass

    def add_file(self, filepath: str) -> None:
        if filepath and filepath not in self._files_changed:
            self._files_changed.append(filepath)
            self.update_files(self._files_changed)


class StatusBar(Widget):
    """Bottom status bar with key info."""
    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    status_text = reactive("Ready")
    model_name = reactive("sonnet")
    cost_text = reactive("$0.00")
    is_streaming = reactive(False)

    def render(self) -> Text:
        parts = []
        if self.is_streaming:
            parts.append(("● streaming ", "bold yellow"))
        else:
            parts.append(("● ready ", "bold green"))
        parts.append((f"│ {self.model_name} ", ""))
        parts.append((f"│ {self.cost_text} ", "dim"))
        parts.append(("│ ?:help  ^n:new  ^p:sessions  ^o:model  ^q:quit", "dim"))
        text = Text()
        for content, style in parts:
            text.append(content, style=style)
        return text


class CommandSuggestions(Widget):
    """Autocomplete dropdown for slash commands."""
    DEFAULT_CSS = """
    CommandSuggestions {
        dock: bottom;
        height: auto;
        max-height: 8;
        margin: 0 1;
        background: $surface;
        border: tall $accent;
        display: none;
        layer: overlay;
    }
    CommandSuggestions .suggestion {
        padding: 0 1;
        height: 1;
    }
    CommandSuggestions .suggestion.highlighted {
        background: $primary-background;
        color: $text;
        text-style: bold;
    }
    """

    suggestions: reactive[list[tuple[str, str]]] = reactive(list, always_update=True)
    selected_index: reactive[int] = reactive(0)

    def render(self) -> Text:
        text = Text()
        for i, (cmd, desc) in enumerate(self.suggestions[:7]):
            prefix = "▸ " if i == self.selected_index else "  "
            style = "bold" if i == self.selected_index else "dim"
            text.append(f"{prefix}{cmd:16s} {desc}\n", style=style)
        return text

    def update_suggestions(self, prefix: str) -> None:
        if not prefix.startswith("/") or " " in prefix:
            self.suggestions = []
            self.display = False
            return
        matches = [(cmd, desc) for cmd, desc in SLASH_COMMANDS if cmd.startswith(prefix)]
        self.suggestions = matches
        self.selected_index = 0
        self.display = bool(matches) and prefix != matches[0][0] if len(matches) == 1 else bool(matches)

    def move_selection(self, delta: int) -> None:
        if self.suggestions:
            self.selected_index = (self.selected_index + delta) % len(self.suggestions)

    def get_selected(self) -> str | None:
        if self.suggestions and 0 <= self.selected_index < len(self.suggestions):
            return self.suggestions[self.selected_index][0]
        return None


class ChatInput(Input):
    """The chat input box with slash command autocomplete."""
    DEFAULT_CSS = """
    ChatInput {
        dock: bottom;
        margin: 0 1;
        border: tall $accent;
    }
    ChatInput:focus {
        border: tall $primary;
    }
    """

    def __init__(self) -> None:
        super().__init__(placeholder="Type a message or /command...", id="chat-input")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update autocomplete suggestions as user types."""
        try:
            suggestions = self.app.query_one(CommandSuggestions)
            suggestions.update_suggestions(event.value.strip())
        except NoMatches:
            pass

    def _on_key(self, event) -> None:
        """Handle Tab/arrow keys for autocomplete."""
        try:
            suggestions = self.app.query_one(CommandSuggestions)
        except NoMatches:
            return

        if not suggestions.suggestions:
            return

        if event.key == "tab":
            selected = suggestions.get_selected()
            if selected:
                self.value = selected + " "
                self.cursor_position = len(self.value)
                suggestions.display = False
            event.prevent_default()
            event.stop()
        elif event.key == "up":
            suggestions.move_selection(-1)
            event.prevent_default()
            event.stop()
        elif event.key == "down":
            suggestions.move_selection(1)
            event.prevent_default()
            event.stop()


# ── Slash Command List ──────────────────────────────────────────

SLASH_COMMANDS = [
    ("/help", "Show available commands"),
    ("/new", "Start a new session"),
    ("/quit", "Exit the REPL"),
    ("/cost", "Show cost breakdown"),
    ("/model", "Show or switch model"),
    ("/status", "System status"),
    ("/memory", "Show MEMORY.md + USER.md"),
    ("/soul", "Show SOUL.md"),
    ("/config", "Show config.yaml"),
    ("/sessions", "List recent sessions"),
    ("/search", "Search conversations"),
    ("/recall", "Search all memory layers"),
    ("/skills", "List installed skills"),
    ("/learnings", "List learnings"),
    ("/heartbeat", "Health check"),
    ("/produce", "Brainstorm ideas"),
    ("/evolve", "Run evolve pipeline"),
    ("/decompose", "Decompose goal into tasks"),
    ("/learn", "Deep-dive a repo/URL/tech"),
    ("/absorb", "Scan + implement improvements"),
    ("/reflect", "Self-analysis"),
    ("/digest", "Morning briefing"),
    ("/gc", "Garbage collection"),
    ("/loop", "Create cron job"),
    ("/loops", "List cron jobs"),
    ("/unloop", "Remove cron job"),
    ("/pause", "Pause cron job"),
    ("/unpause", "Resume cron job"),
    ("/notify", "Delayed notification"),
    ("/queue", "Pending approvals"),
    ("/approve", "Approve skill"),
    ("/reject", "Reject skill"),
    ("/autonomy", "Show/set autonomy"),
    ("/wechat", "WeChat digest"),
    ("/discord", "Discord digest"),
    ("/whatsapp", "WhatsApp digest"),
    ("/lang", "Set output language"),
    ("/do", "Natural language → command"),
    ("/restart", "Restart the gateway"),
    ("/speak", "Text-to-speech"),
    ("/subscribe", "Manage digest subscriptions"),
    ("/serve", "Manage serve targets"),
]


# ── Help Screen ─────────────────────────────────────────────────

class HelpScreen(ModalScreen[None]):
    """Modal overlay showing all keybindings and commands."""
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 80;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    HelpScreen .help-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin-bottom: 1;
    }
    HelpScreen .help-section {
        text-style: bold;
        color: $secondary;
        margin-top: 1;
    }
    """
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("agenticEvolve — Help", classes="help-title")

            yield Static("KEYBINDINGS", classes="help-section")
            yield Static(
                "  Ctrl+N    New session       Ctrl+P    Switch session\n"
                "  Ctrl+O    Switch model      Ctrl+Q    Quit\n"
                "  Tab       Accept suggestion  Escape    Cancel / close\n"
                "  Enter     Send message       PgUp/Dn  Scroll messages"
            )

            _categories = {
                "Session": ["/help", "/new", "/quit"],
                "Info": ["/cost", "/model", "/status", "/memory", "/soul",
                         "/config", "/sessions", "/search", "/recall",
                         "/skills", "/learnings", "/heartbeat"],
                "Pipelines": ["/produce", "/evolve", "/decompose", "/learn",
                              "/absorb", "/reflect", "/digest", "/gc"],
                "Cron": ["/loop", "/loops", "/unloop", "/pause", "/unpause", "/notify"],
                "Approval": ["/queue", "/approve", "/reject"],
                "Admin": ["/autonomy", "/restart"],
                "Platform Digests": ["/wechat", "/discord", "/whatsapp"],
                "Subscriptions": ["/subscribe", "/serve"],
                "Utilities": ["/lang", "/do", "/speak"],
            }
            _cmd_map = {cmd: desc for cmd, desc in SLASH_COMMANDS}

            for category, cmds in _categories.items():
                yield Static(category.upper(), classes="help-section")
                lines = []
                for cmd in cmds:
                    desc = _cmd_map.get(cmd, "")
                    lines.append(f"  {cmd:16s} {desc}")
                yield Static("\n".join(lines))

            yield Static("\n[dim]Press Escape to close[/dim]")


# ── Session Picker Screen ──────────────────────────────────────

class SessionScreen(ModalScreen[str]):
    """Pick a session to resume."""
    DEFAULT_CSS = """
    SessionScreen {
        align: center middle;
    }
    SessionScreen > Vertical {
        width: 80;
        max-height: 70%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    SessionScreen .session-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin-bottom: 1;
    }
    SessionScreen .session-item {
        padding: 0 1;
        height: 1;
    }
    SessionScreen .session-item:hover {
        background: $primary-background;
    }
    """
    BINDINGS = [Binding("escape", "dismiss('')", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Switch Session", classes="session-title")
            sessions = list_sessions(limit=15)
            if not sessions:
                yield Static("[dim]No sessions found[/dim]")
            else:
                for s in sessions:
                    sid = s.get("id", "?")
                    title = s.get("title", "untitled")[:40]
                    msgs = s.get("message_count", 0)
                    ts = s.get("started_at", "")[:16]
                    btn = Static(
                        f"  {ts}  {msgs:3d} msgs  {title}",
                        classes="session-item",
                    )
                    btn.session_id = sid
                    yield btn
            yield Static("\n[dim]Press Escape to close[/dim]")


# ── Model Picker Screen ────────────────────────────────────────

class ModelScreen(ModalScreen[str]):
    """Pick a model."""
    DEFAULT_CSS = """
    ModelScreen {
        align: center middle;
    }
    ModelScreen > Vertical {
        width: 50;
        max-height: 50%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    ModelScreen .model-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin-bottom: 1;
    }
    """
    BINDINGS = [Binding("escape", "dismiss('')", "Close")]

    MODELS = ["sonnet", "opus", "haiku"]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Switch Model", classes="model-title")
            yield Input(placeholder="Type model name (sonnet/opus/haiku)...", id="model-input")
            yield Static("\n[dim]Enter to select, Escape to cancel[/dim]")

    @on(Input.Submitted, "#model-input")
    def on_submit(self, event: Input.Submitted) -> None:
        model = event.value.strip().lower()
        if model:
            self.dismiss(model)


# ── Main App ────────────────────────────────────────────────────

class AEApp(App):
    """agenticEvolve interactive TUI."""

    TITLE = "agenticEvolve"
    SUB_TITLE = "interactive agent"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 1fr;
        layout: horizontal;
    }

    #chat-pane {
        width: 1fr;
        layout: vertical;
    }

    #messages-scroll {
        height: 1fr;
        scrollbar-gutter: stable;
    }

    #messages {
        padding: 0 0;
        height: auto;
    }

    #input-area {
        dock: bottom;
        height: auto;
        max-height: 4;
        padding: 0 1;
    }

    Sidebar {
        width: 32;
    }

    .streaming-indicator {
        color: $warning;
        text-style: italic;
        margin: 0 1 0 2;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        Binding("ctrl+n", "new_session", "New Session", show=True),
        Binding("ctrl+p", "switch_session", "Sessions", show=True),
        Binding("ctrl+o", "switch_model", "Model", show=True),
        Binding("escape", "cancel_stream", "Cancel", show=False),
    ]

    is_streaming = reactive(False)

    def __init__(self, resume_session: str = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = load_config()
        self._state = SessionState(self._config)
        self._resume_session = resume_session
        self._stream_proc: subprocess.Popen | None = None
        self._current_assistant: AssistantMessage | None = None
        self._current_text_parts: list[str] = []
        self._stream_buffer: str = ""
        self._files_modified: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="chat-pane"):
                with VerticalScroll(id="messages-scroll"):
                    yield Vertical(id="messages")
                yield CommandSuggestions()
                yield ChatInput()
            yield Sidebar(self._state)
        yield StatusBar()

    def on_mount(self) -> None:
        """Initialize after mount."""
        sb = self.query_one(StatusBar)
        sb.model_name = self._state.model
        sb.cost_text = f"${self._state.session_cost:.4f}"

        sidebar = self.query_one(Sidebar)
        sidebar.refresh_info()

        # Resume session if requested
        if self._resume_session:
            messages = get_session_messages(self._resume_session)
            if messages:
                self._state.session_id = self._resume_session
                self._state.history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in messages
                ]
                self._state.message_count = len(messages)
                # Render existing messages
                container = self.query_one("#messages", Vertical)
                for m in messages:
                    if m["role"] == "user":
                        container.mount(UserMessage(escape(m["content"])))
                    else:
                        container.mount(AssistantMessage(m["content"]))
                self._scroll_to_bottom()
                sidebar.refresh_info()

        # Focus input
        self.query_one(ChatInput).focus()

    def on_click(self, event) -> None:
        """Always keep focus on the input bar."""
        self.query_one(ChatInput).focus()

    # ── Input handling ──────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input."""
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if self.is_streaming:
            return

        # Slash commands
        if text.startswith("/"):
            self._handle_command(text)
            return

        # Check cost cap
        cap = self._check_cost_cap()
        if cap:
            self._add_system_message(f"[bold red]{cap}[/bold red]")
            return

        # Regular chat message
        self._state.add_user_message(text)
        container = self.query_one("#messages", Vertical)
        container.mount(UserMessage(escape(text)))
        self._scroll_to_bottom()

        # Update sidebar
        self.query_one(Sidebar).refresh_info()

        # Start streaming
        self._start_stream(text)

    # ── Streaming ───────────────────────────────────────────────

    @work(thread=True)
    def _start_stream(self, message: str) -> None:
        """Stream response from Claude in a background thread."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)

        config = self._state.config
        system_prompt = build_system_prompt(config)

        allowed_tools = None
        try:
            from gateway.autonomy import resolve_tools
            allowed_tools = resolve_tools(config)
        except Exception:
            pass

        prompt_parts = []
        ctx = f"[Gateway: platform=cli, session={self._state.session_id}]"
        prompt_parts.append(ctx)

        if self._state.history:
            formatted = _format_history(self._state.history)
            if formatted:
                prompt_parts.append(
                    "# Conversation history (for context — do NOT repeat or summarize it, "
                    "just use it to understand what was discussed):\n\n" + formatted
                )

        # Auto-recall
        try:
            recall_query = message.strip()
            if len(recall_query) > 15 and not recall_query.startswith("/"):
                results = unified_search(
                    recall_query[:200],
                    session_id=self._state.session_id,
                    limit_per_layer=2,
                )
                recall_block = format_recall_context(results, max_chars=1500)
                if recall_block:
                    prompt_parts.append(recall_block)
        except Exception:
            pass

        prompt_parts.append(f"# Current message:\n\n{message}")
        full_prompt = "\n\n---\n\n".join(prompt_parts)

        cmd = [
            "claude", "-p", full_prompt,
            "--model", self._state.model,
            "--output-format", "stream-json",
            "--verbose",
            "--no-chrome",
            "--mcp-config", '{"mcpServers":{}}',
            "--strict-mcp-config",
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

        text_parts = []
        cost = 0.0

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=work_dir,
                env=env,
            )
            self._stream_proc = proc

            for line in proc.stdout:
                if proc.poll() is not None and not line.strip():
                    break
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
                                self.call_from_thread(
                                    self.post_message,
                                    StreamToken(text),
                                )
                            elif block.get("type") == "tool_use":
                                name = block.get("name", "tool")
                                input_data = block.get("input", {})
                                self.call_from_thread(
                                    self.post_message,
                                    ToolStart(name, input_data),
                                )
                                # Track file modifications
                                if name in ("Write", "Edit"):
                                    fp = input_data.get("file_path") or input_data.get("filePath", "")
                                    if fp:
                                        self._files_modified.append(fp)
                                        self.call_from_thread(
                                            self._update_sidebar_files,
                                        )

                    elif msg_type == "user":
                        # Tool result — mark tool as done
                        self.call_from_thread(
                            self.post_message,
                            ToolEnd(),
                        )

                    elif msg_type == "result":
                        result_text = obj.get("result", "")
                        if result_text:
                            if not text_parts:
                                text_parts.append(result_text)
                            else:
                                text_parts[-1] = result_text
                            self.call_from_thread(
                                self.post_message,
                                StreamToken(result_text),
                            )
                        cost = obj.get("total_cost_usd", 0)

                except json.JSONDecodeError:
                    continue

            proc.wait()

        except Exception as e:
            text_parts = [f"Error: {e}"]
            cost = 0

        finally:
            self._stream_proc = None
            self.is_streaming = False

        final_text = text_parts[-1] if text_parts else ""
        self.call_from_thread(
            self.post_message,
            StreamDone(final_text, cost, bool(text_parts)),
        )

    def _update_sidebar_files(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.update_files(self._files_modified)

    def _update_status_bar(self) -> None:
        sb = self.query_one(StatusBar)
        sb.is_streaming = self.is_streaming
        sb.model_name = self._state.model
        sb.cost_text = f"${self._state.session_cost:.4f}"

    # ── Message handlers ────────────────────────────────────────

    def on_stream_token(self, event: StreamToken) -> None:
        """Handle a streamed token — update or create assistant message."""
        container = self.query_one("#messages", Vertical)
        if self._current_assistant is None:
            self._current_assistant = AssistantMessage(event.text)
            self._current_text_parts = [event.text]
            container.mount(self._current_assistant)
        else:
            self._current_text_parts.append(event.text)
            # Re-render with latest text part only (last block from Claude)
            self._current_assistant.update_content(event.text)
        self._scroll_to_bottom()

    def on_tool_start(self, event: ToolStart) -> None:
        """Show tool execution panel."""
        container = self.query_one("#messages", Vertical)
        panel = ToolPanel(event.name, event.input_data, active=True)
        container.mount(panel)
        self._scroll_to_bottom()

    def on_tool_end(self, event: ToolEnd) -> None:
        """Mark tool as completed (could update the panel)."""
        # The next StreamToken will create a new assistant message block
        self._current_assistant = None

    def on_stream_done(self, event: StreamDone) -> None:
        """Streaming finished."""
        self._current_assistant = None
        self._current_text_parts = []
        self.is_streaming = False
        self._update_status_bar()

        if event.success:
            self._state.add_assistant_message(event.text, event.cost)
            # Update sidebar
            self.query_one(Sidebar).refresh_info()
            # Cost indicator
            if event.cost > 0:
                container = self.query_one("#messages", Vertical)
                container.mount(
                    Static(
                        f"[dim]${event.cost:.4f} │ session: ${self._state.session_cost:.4f}[/dim]",
                    )
                )
                # Update status bar
                sb = self.query_one(StatusBar)
                sb.cost_text = f"${self._state.session_cost:.4f}"
        else:
            self._add_system_message("[red]Request failed.[/red]")

        self._scroll_to_bottom()
        self.query_one(ChatInput).focus()

    def on_command_output(self, event: CommandOutput) -> None:
        """Display command output in the messages area."""
        container = self.query_one("#messages", Vertical)
        if event.is_markdown:
            container.mount(AssistantMessage(event.content))
        else:
            container.mount(Static(event.content))
        self._scroll_to_bottom()

    # ── Helpers ─────────────────────────────────────────────────

    def _add_system_message(self, markup: str) -> None:
        container = self.query_one("#messages", Vertical)
        container.mount(Static(markup))
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        def _do_scroll() -> None:
            try:
                scroll = self.query_one("#messages-scroll", VerticalScroll)
                scroll.scroll_end(animate=False)
            except NoMatches:
                pass
        self.call_after_refresh(_do_scroll)

    def _check_cost_cap(self) -> str | None:
        config = self._state.config
        caps = config.get("cost_caps", {})
        daily_cap = caps.get("daily_usd", 999999)
        try:
            today_cost = get_today_cost()
            if today_cost >= daily_cap:
                return f"Daily cost cap reached (${today_cost:.2f} / ${daily_cap:.2f})"
        except Exception:
            pass
        return None

    # ── Actions ─────────────────────────────────────────────────

    def action_quit_app(self) -> None:
        self._state.end()
        self.exit()

    def action_new_session(self) -> None:
        self._state.new_session()
        # Clear messages
        container = self.query_one("#messages", Vertical)
        container.remove_children()
        self._files_modified = []
        self._add_system_message(
            f"[green]New session: {self._state.session_id}[/green]"
        )
        self.query_one(Sidebar).refresh_info()
        self.query_one(Sidebar).update_files([])
        self._update_status_bar()
        self.query_one(ChatInput).focus()

    def action_switch_session(self) -> None:
        def on_result(session_id: str | None) -> None:
            if session_id:
                self._resume_to(session_id)
        self.push_screen(SessionScreen(), callback=on_result)

    def action_switch_model(self) -> None:
        def on_result(model: str | None) -> None:
            if model:
                self._state.model = model
                self._add_system_message(f"[green]Switched to {model}[/green]")
                self._update_status_bar()
                self.query_one(Sidebar).refresh_info()
        self.push_screen(ModelScreen(), callback=on_result)

    def action_cancel_stream(self) -> None:
        if self._stream_proc:
            try:
                self._stream_proc.send_signal(signal.SIGTERM)
            except Exception:
                pass
            self._add_system_message("[yellow]Cancelled.[/yellow]")

    def _resume_to(self, session_id: str) -> None:
        messages = get_session_messages(session_id)
        if not messages:
            self._add_system_message(f"[yellow]Session {session_id} not found[/yellow]")
            return
        self._state.session_id = session_id
        self._state.history = [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]
        self._state.message_count = len(messages)
        self._state.session_cost = 0.0

        container = self.query_one("#messages", Vertical)
        container.remove_children()
        for m in messages:
            if m["role"] == "user":
                container.mount(UserMessage(escape(m["content"])))
            else:
                container.mount(AssistantMessage(m["content"]))

        self._add_system_message(
            f"[green]Resumed: {session_id} ({len(messages)} messages)[/green]"
        )
        self.query_one(Sidebar).refresh_info()
        self._scroll_to_bottom()

    # ── Slash Commands ──────────────────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        """Route slash commands."""
        parts = cmd.strip().split(None, 1)
        name = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if name in ("/help", "/h", "/?"):
            self.push_screen(HelpScreen())

        elif name in ("/new", "/newsession"):
            self.action_new_session()

        elif name in ("/quit", "/q", "/exit"):
            self.action_quit_app()

        elif name in ("/cost", "/c"):
            self._cmd_cost()

        elif name in ("/model", "/m"):
            if arg:
                self._state.model = arg.strip().lower()
                self._add_system_message(f"[green]Model: {self._state.model}[/green]")
                self._update_status_bar()
                self.query_one(Sidebar).refresh_info()
            else:
                self.action_switch_model()

        elif name in ("/status",):
            self._cmd_status()

        elif name in ("/memory", "/mem"):
            self._cmd_memory()

        elif name in ("/soul",):
            self._cmd_soul()

        elif name in ("/config",):
            self._cmd_config()

        elif name in ("/sessions", "/s"):
            self._cmd_sessions(arg)

        elif name in ("/search",):
            self._cmd_search(arg)

        elif name in ("/recall",):
            self._cmd_recall(arg)

        elif name in ("/skills",):
            self._cmd_skills()

        elif name in ("/learnings",):
            self._cmd_learnings(arg)

        elif name in ("/heartbeat",):
            self._cmd_heartbeat()

        # Pipeline commands — route to chat (LLM handles them)
        elif name in ("/produce", "/evolve", "/decompose", "/learn",
                       "/absorb", "/reflect", "/digest", "/gc"):
            self._cmd_pipeline(name, arg)

        # Cron
        elif name in ("/loop", "/loops", "/unloop", "/pause", "/unpause", "/notify"):
            self._cmd_cron(name, arg)

        # Approval
        elif name in ("/queue", "/approve", "/reject"):
            self._cmd_approval(name, arg)

        # Admin
        elif name in ("/autonomy",):
            self._cmd_autonomy(arg)

        # Platform digests
        elif name in ("/wechat", "/discord", "/whatsapp"):
            self._cmd_platform_digest(name, arg)

        # Language
        elif name in ("/lang",):
            self._cmd_lang(arg)

        # Natural language → command
        elif name in ("/do",):
            self._cmd_do(arg)

        # Restart gateway
        elif name in ("/restart",):
            self._cmd_restart()

        # Text-to-speech
        elif name in ("/speak",):
            self._cmd_speak(arg)

        # Subscriptions
        elif name in ("/subscribe",):
            self._cmd_subscribe(arg)

        elif name in ("/serve",):
            self._cmd_serve(arg)

        else:
            self._add_system_message(f"[yellow]Unknown command: {name}[/yellow]")

    # ── Command implementations ─────────────────────────────────

    def _cmd_cost(self) -> None:
        try:
            today = get_today_cost()
            week = get_week_cost()
            caps = self._state.config.get("cost_caps", {})
            daily_cap = caps.get("daily_usd", 999999)
            msg = (
                f"**Cost**\n"
                f"- Session: ${self._state.session_cost:.4f}\n"
                f"- Today: ${today:.4f} / ${daily_cap:.2f}\n"
                f"- Week: ${week:.4f}\n"
            )
            self.post_message(CommandOutput(msg, is_markdown=True))
        except Exception as e:
            self._add_system_message(f"[red]Error: {e}[/red]")

    def _cmd_status(self) -> None:
        try:
            s = stats()
            today = get_today_cost()
            msg = (
                f"**Status**\n"
                f"- Sessions: {s.get('total_sessions', 0)}\n"
                f"- Messages: {s.get('total_messages', 0)}\n"
                f"- DB: {s.get('db_size_mb', '?')} MB\n"
                f"- Cost today: ${today:.4f}\n"
                f"- Model: {self._state.model}\n"
                f"- Session: `{self._state.session_id}`\n"
            )
            self.post_message(CommandOutput(msg, is_markdown=True))
        except Exception as e:
            self._add_system_message(f"[red]Error: {e}[/red]")

    def _cmd_memory(self) -> None:
        mem_path = EXODIR / "memory" / "MEMORY.md"
        user_path = EXODIR / "memory" / "USER.md"
        parts = []
        for label, path in [("MEMORY.md", mem_path), ("USER.md", user_path)]:
            if path.exists():
                content = path.read_text().strip()
                chars = len(content)
                limit = 2200 if "MEMORY" in label else 1375
                parts.append(f"### {label} ({chars}/{limit} chars)\n\n{content}")
            else:
                parts.append(f"### {label}\n\n*Not found*")
        self.post_message(CommandOutput("\n\n---\n\n".join(parts), is_markdown=True))

    def _cmd_soul(self) -> None:
        soul_path = EXODIR / "SOUL.md"
        if soul_path.exists():
            content = soul_path.read_text().strip()
            self.post_message(CommandOutput(content, is_markdown=True))
        else:
            self._add_system_message("[yellow]SOUL.md not found[/yellow]")

    def _cmd_config(self) -> None:
        config_path = EXODIR / "config.yaml"
        if config_path.exists():
            content = config_path.read_text().strip()
            self.post_message(CommandOutput(f"```yaml\n{content}\n```", is_markdown=True))
        else:
            self._add_system_message("[yellow]config.yaml not found[/yellow]")

    def _cmd_sessions(self, arg: str) -> None:
        try:
            limit = int(arg) if arg.strip().isdigit() else 10
        except ValueError:
            limit = 10
        sessions = list_sessions(limit=limit)
        if not sessions:
            self._add_system_message("[dim]No sessions[/dim]")
            return
        lines = ["| Date | Messages | Title |", "| --- | --- | --- |"]
        for s in sessions:
            ts = s.get("started_at", "")[:16]
            msgs = s.get("message_count", 0)
            title = s.get("title", "untitled")[:40]
            sid = s.get("id", "?")[:16]
            lines.append(f"| {ts} | {msgs} | {title} |")
        self.post_message(CommandOutput("\n".join(lines), is_markdown=True))

    def _cmd_search(self, arg: str) -> None:
        if not arg.strip():
            self._add_system_message("[yellow]Usage: /search <query>[/yellow]")
            return
        results = search_sessions(arg.strip(), limit=5)
        if not results:
            self._add_system_message("[dim]No results[/dim]")
            return
        parts = []
        for r in results:
            sid = r.get("session_id", "?")[:16]
            src = r.get("source", "?")
            matches = r.get("matches", [])[:3]
            lines = [f"**{sid}** ({src})"]
            for m in matches:
                role = m.get("role", "?")
                text = m.get("content", "")[:150]
                lines.append(f"  [{role}] {text}")
            parts.append("\n".join(lines))
        self.post_message(CommandOutput("\n\n---\n\n".join(parts), is_markdown=True))

    def _cmd_recall(self, arg: str) -> None:
        if not arg.strip():
            self._add_system_message("[yellow]Usage: /recall <query>[/yellow]")
            return
        results = unified_search(arg.strip(), limit_per_layer=3)
        block = format_recall_context(results, max_chars=3000)
        if block:
            self.post_message(CommandOutput(block, is_markdown=True))
        else:
            self._add_system_message("[dim]No recall results[/dim]")

    def _cmd_skills(self) -> None:
        skills_dir = Path.home() / ".claude" / "skills"
        if not skills_dir.exists():
            self._add_system_message("[dim]No skills installed[/dim]")
            return
        skills = sorted(skills_dir.iterdir())
        if not skills:
            self._add_system_message("[dim]No skills installed[/dim]")
            return
        lines = ["**Installed Skills**\n"]
        for s in skills:
            if s.is_dir() and (s / "SKILL.md").exists():
                lines.append(f"- `{s.name}`")
        self.post_message(CommandOutput("\n".join(lines), is_markdown=True))

    def _cmd_learnings(self, arg: str) -> None:
        from gateway.session_db import list_learnings as get_learnings
        try:
            limit = int(arg) if arg.strip().isdigit() else 10
        except ValueError:
            limit = 10
        rows = get_learnings(limit=limit)
        if not rows:
            self._add_system_message("[dim]No learnings[/dim]")
            return
        lines = ["**Recent Learnings**\n"]
        for r in rows:
            ts = r.get("created_at", "")[:16]
            text = r.get("content", "")[:100]
            lines.append(f"- [{ts}] {text}")
        self.post_message(CommandOutput("\n".join(lines), is_markdown=True))

    def _cmd_heartbeat(self) -> None:
        import shutil
        disk = shutil.disk_usage(str(EXODIR))
        disk_gb = disk.free / (1024**3)
        try:
            today = get_today_cost()
        except Exception:
            today = 0
        msg = (
            f"**Heartbeat**\n"
            f"- Status: OK\n"
            f"- Model: {self._state.model}\n"
            f"- Session: `{self._state.session_id[:16]}`\n"
            f"- Cost today: ${today:.4f}\n"
            f"- Disk free: {disk_gb:.1f} GB\n"
        )
        self.post_message(CommandOutput(msg, is_markdown=True))

    def _cmd_pipeline(self, name: str, arg: str) -> None:
        """Run a pipeline command with proper implementation."""
        if name == "/produce":
            self._run_produce(arg)
        elif name == "/evolve":
            self._run_evolve(arg)
        elif name == "/decompose":
            self._run_decompose(arg)
        elif name == "/learn":
            self._run_learn(arg)
        elif name == "/absorb":
            self._run_absorb(arg)
        elif name == "/reflect":
            self._run_reflect(arg)
        elif name == "/digest":
            self._cmd_digest(arg)
        elif name == "/gc":
            self._cmd_gc(arg)

    @work(thread=True)
    def _run_produce(self, arg: str) -> None:
        """Aggregate signals and brainstorm business ideas."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        self.call_from_thread(
            self._add_system_message, "[dim]Aggregating signals, brainstorming ideas...[/dim]"
        )
        try:
            from gateway.cli import _cmd_produce as _cli_produce, SessionState as _CliState
            # Use _invoke_claude_streaming directly
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
                self.call_from_thread(
                    self._add_system_message,
                    "[yellow]No signals found for today. Run /evolve first.[/yellow]"
                )
                return
            source_summaries = []
            for source_name, count in sorted(source_counts.items()):
                source_signals = [s for s in all_signals
                                  if s.get("source", "") in (source_name.replace("-", ""), source_name)
                                  or s.get("id", "").startswith(source_name.split("-")[0])]
                source_signals.sort(
                    key=lambda x: (x.get("metadata", {}).get("points", 0) or
                                   x.get("metadata", {}).get("stars", 0) or 0),
                    reverse=True
                )
                items = []
                for s in source_signals[:8]:
                    title = s.get("title", "")
                    content = s.get("content", "")[:200]
                    url = s.get("url", "")
                    engagement = (s.get("metadata", {}).get("points", 0) or
                                  s.get("metadata", {}).get("stars", 0) or 0)
                    items.append(f"  - {title} ({engagement} pts) {url}\n    {content}")
                if items:
                    source_summaries.append(f"### {source_name} ({count} signals)\n" + "\n".join(items))
            signals_text = "\n\n".join(source_summaries)
            if len(signals_text) > 40000:
                signals_text = signals_text[:40000] + "\n\n... (truncated)"
            num_ideas = 5
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
                prompt, on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context=f"[Produce: {num_ideas} ideas from {len(all_signals)} signals]"
            )
            text = result.get("text", "No ideas generated.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(text, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="produce")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Produce failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_evolve(self, arg: str) -> None:
        """Run the multi-stage evolve pipeline."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        dry_run = "--dry-run" in arg or "--dry" in arg
        stages = "COLLECT -> ANALYZE" if dry_run else "COLLECT -> ANALYZE -> BUILD -> REVIEW -> REPORT"
        self.call_from_thread(
            self._add_system_message,
            f"[dim]Evolving... {stages} (~{'2-4' if dry_run else '5-10'} min)[/dim]"
        )
        try:
            from gateway.evolve import EvolveOrchestrator
            orchestrator = EvolveOrchestrator(
                model=self._state.model,
                on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
            )
            summary, cost = orchestrator.run(dry_run=dry_run)
            self._state.add_assistant_message(summary, cost)
            self.call_from_thread(self.post_message, CommandOutput(summary, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="evolve")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Evolve failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_decompose(self, arg: str) -> None:
        """Decompose a goal into tasks."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        goal = arg.replace("--dry-run", "").replace("--dry", "").strip()
        if not goal:
            self.call_from_thread(
                self._add_system_message,
                "[yellow]Usage: /decompose <goal>[/yellow]"
            )
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)
            return
        dry_run = "--dry-run" in arg or "--dry" in arg
        self.call_from_thread(
            self._add_system_message,
            f"[dim]Decomposing: {goal[:60]}...[/dim]"
        )
        try:
            system_context = (
                "You are the DECOMPOSE agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
                "Our system: Python asyncio gateway → Claude Code (claude -p) → Telegram. "
                "Skills in ~/.claude/skills/, memory in ~/.agenticEvolve/memory/.\n\n"
            )
            planner_prompt = (
                system_context +
                f"GOAL: {goal}\n\n"
                f"Break this into parallel-executable tasks. Output a task DAG as JSON, then implement.\n"
            )
            if dry_run:
                planner_prompt += "\nDRY RUN: Output the DAG only. Do NOT implement.\n"
            result = _invoke_claude_streaming(
                planner_prompt,
                on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context=f"[Decompose: {goal[:50]}]",
            )
            text = result.get("text", "No output.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(text, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="decompose")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Decompose failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_learn(self, arg: str) -> None:
        """Deep-dive a repo/URL/tech."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        target = arg.replace("--dry-run", "").replace("--dry", "").strip()
        if not target:
            self.call_from_thread(
                self._add_system_message,
                "[yellow]Usage: /learn <repo-url or tech>[/yellow]"
            )
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)
            return
        self.call_from_thread(
            self._add_system_message,
            f"[dim]Learning: {target[:60]}... (~3-6 min)[/dim]"
        )
        try:
            is_github = "github.com" in target
            is_url = target.startswith("http://") or target.startswith("https://")
            system_context = (
                "You are the LEARN agent for agenticEvolve — Vincent's personal closed-loop agent system.\n\n"
                "Vincent builds AI agents, onchain infrastructure, and developer tools.\n\n"
            )
            analysis = (
                "EXTRACT PATTERNS: design patterns, architectural decisions, stealable techniques.\n"
                "EVALUATE: ADOPT / STEAL / SKIP verdict. If ADOPT or STEAL, create a skill.\n"
                "Update MEMORY.md with findings.\n"
            )
            if is_github:
                prompt = system_context + f"Deep-dive this GitHub repo: {target}\n\n" + analysis
            elif is_url:
                prompt = system_context + f"Research this URL: {target}\n\n" + analysis
            else:
                prompt = system_context + f"Research this technology: {target}\n\n" + analysis
            result = _invoke_claude_streaming(
                prompt, on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context=f"[Learn: {target[:50]}]"
            )
            text = result.get("text", "No output.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(text, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="learn")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Learn failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_absorb(self, arg: str) -> None:
        """Scan + implement improvements from a target."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        target = arg.replace("--dry-run", "").replace("--dry", "").strip()
        if not target:
            self.call_from_thread(
                self._add_system_message,
                "[yellow]Usage: /absorb <repo-url or tech>[/yellow]"
            )
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)
            return
        dry_run = "--dry-run" in arg or "--dry" in arg
        is_github = "github.com" in target
        is_url = target.startswith("http://") or target.startswith("https://")
        target_type = "github" if is_github else ("url" if is_url else "topic")
        self.call_from_thread(
            self._add_system_message,
            f"[dim]Absorbing: {target[:60]} (~{'3-5' if dry_run else '8-15'} min)[/dim]"
        )
        try:
            from gateway.absorb import AbsorbOrchestrator
            orchestrator = AbsorbOrchestrator(
                target=target, target_type=target_type, model=self._state.model,
                on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
            )
            summary, cost = orchestrator.run(dry_run=dry_run)
            self._state.add_assistant_message(summary, cost)
            self.call_from_thread(self.post_message, CommandOutput(summary, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="absorb")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Absorb failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_reflect(self, arg: str) -> None:
        """Self-analysis: patterns, gaps, next actions."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        days = 7
        self.call_from_thread(
            self._add_system_message,
            f"[dim]Reflecting on the last {days} days... ~2-4 min[/dim]"
        )
        try:
            now = datetime.now(timezone.utc)
            since = (now - timedelta(days=days)).isoformat()
            prompt = (
                f"You are the REFLECT agent for agenticEvolve.\n\n"
                f"Run a {days}-day self-analysis:\n"
                f"1. Query SQLite DB at {EXODIR}/memory/sessions.db for sessions since {since}\n"
                f"2. Check git log in ~/Desktop/projects/agenticEvolve since {since[:10]}\n"
                f"3. List skills in ~/.claude/skills/\n"
                f"4. Read MEMORY.md and USER.md\n"
                f"5. Return: patterns, avoidance, 3 things to build next, system health\n"
            )
            result = _invoke_claude_streaming(
                prompt, on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context="[Reflect pipeline]"
            )
            text = result.get("text", "No output.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(
                f"**Reflect — last {days}d**\n\n{text}", is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="reflect")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Reflect failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    def _cmd_digest(self, arg: str) -> None:
        """Morning briefing: sessions, signals, cost, skills, cron."""
        import sqlite3
        from gateway.session_db import DB_PATH
        from gateway.commands.cron_core import CRON_JOBS_FILE
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=1)
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
        text = (
            f"**Digest — {now.strftime('%Y-%m-%d %H:%M')} UTC**\n\n"
            f"**Sessions (today):**\n{sessions_summary}\n\n"
            f"**Top signals:**\n{signals_summary}\n\n"
            f"**Skills built (today):**\n{skills_built}\n\n"
            f"**Cost today:** ${cost_today:.2f}\n\n"
            f"**Cron (next runs):**\n{cron_summary}"
        )
        self.post_message(CommandOutput(text, is_markdown=True))

    def _cmd_gc(self, arg: str) -> None:
        """Run garbage collection."""
        dry_run = "--dry-run" in arg or "--dry" in arg
        try:
            from gateway.gc import run_gc, format_gc_report
            self._add_system_message(f"[dim]Running GC{' (dry run)' if dry_run else ''}...[/dim]")
            report = run_gc(dry_run=dry_run)
            text = format_gc_report(report)
            self.post_message(CommandOutput(text, is_markdown=True))
        except Exception as e:
            self._add_system_message(f"[red]GC failed: {e}[/red]")

    def _cmd_cron(self, name: str, arg: str) -> None:
        """Handle cron commands locally."""
        from gateway.commands.cron_core import load_cron_jobs
        if name == "/loops":
            jobs = load_cron_jobs()
            if not jobs:
                self._add_system_message("[dim]No cron jobs[/dim]")
                return
            lines = ["**Active Cron Jobs**\n"]
            for j in jobs:
                status = "paused" if j.get("paused") else "active"
                lines.append(
                    f"- `{j.get('id', '?')[:8]}` [{status}] "
                    f"every {j.get('interval', '?')}s — {j.get('prompt', '')[:50]}"
                )
            self.post_message(CommandOutput("\n".join(lines), is_markdown=True))
        else:
            self._add_system_message(
                f"[yellow]{name} requires gateway process (use Telegram)[/yellow]"
            )

    def _cmd_approval(self, name: str, arg: str) -> None:
        """Handle approval commands."""
        queue_dir = EXODIR / "skills-queue"
        if name == "/queue":
            if not queue_dir.exists():
                self._add_system_message("[dim]No skills pending[/dim]")
                return
            pending = [d for d in queue_dir.iterdir() if d.is_dir()]
            if not pending:
                self._add_system_message("[dim]No skills pending[/dim]")
                return
            lines = ["**Pending Skills**\n"]
            for p in pending:
                lines.append(f"- `{p.name}`")
            self.post_message(CommandOutput("\n".join(lines), is_markdown=True))
        else:
            self._add_system_message(
                f"[yellow]{name} {arg} — use Telegram for approval flow[/yellow]"
            )

    def _cmd_autonomy(self, arg: str) -> None:
        current = self._state.config.get("autonomy", "supervised")
        if not arg.strip():
            self._add_system_message(f"Autonomy: [bold]{current}[/bold]")
        else:
            self._add_system_message(
                "[yellow]Edit config.yaml to change autonomy level[/yellow]"
            )

    def _cmd_platform_digest(self, name: str, arg: str) -> None:
        """Route to proper platform digest."""
        if name == "/wechat":
            self._run_wechat_digest(arg)
        elif name == "/discord":
            self._run_discord_digest(arg)
        elif name == "/whatsapp":
            self._run_whatsapp_digest(arg)

    @work(thread=True)
    def _run_wechat_digest(self, arg: str) -> None:
        """WeChat group chat digest."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        hours = 24
        self.call_from_thread(
            self._add_system_message,
            f"[dim]Reading WeChat groups (last {hours}h)...[/dim]"
        )
        try:
            tools_dir = Path.home() / ".agenticEvolve" / "tools" / "wechat-decrypt"
            decrypted_dir = tools_dir / "decrypted"
            if not decrypted_dir.exists():
                self.call_from_thread(
                    self._add_system_message,
                    "[yellow]No decrypted WeChat data found.[/yellow]"
                )
                return
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "wechat_collector",
                str(Path.home() / ".agenticEvolve" / "collectors" / "wechat.py")
            )
            wechat_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wechat_mod)
            signals = wechat_mod.extract_group_messages(decrypted_dir, hours=hours)
            if not signals:
                self.call_from_thread(
                    self._add_system_message,
                    f"[dim]No WeChat messages in the last {hours}h.[/dim]"
                )
                return
            chat_lines = []
            total_msgs = 0
            for s in signals:
                meta = s.get("metadata", {})
                chat_lines.append(f"## {meta.get('group_name', 'Unknown')} "
                                  f"({meta.get('message_count', 0)} msgs)")
                chat_lines.append(s.get("content", ""))
                total_msgs += meta.get("message_count", 0)
            chat_text = "\n".join(chat_lines)
            if len(chat_text) > 30000:
                chat_text = chat_text[:30000] + "\n\n... (truncated)"
            prompt = (
                f"Analyze WeChat group chats ({total_msgs} msgs, {len(signals)} groups, last {hours}h):\n\n"
                f"{chat_text}\n\n"
                f"Digest each group separately. 简体中文. Markdown."
            )
            result = _invoke_claude_streaming(
                prompt, on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context=f"[WeChat digest: {hours}h]"
            )
            text = result.get("text", "No analysis.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(text, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="wechat")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]WeChat digest failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_discord_digest(self, arg: str) -> None:
        """Discord channel digest from platform_messages."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        hours = 24
        try:
            from gateway.session_db import get_platform_messages, get_subscriptions
            subs = get_subscriptions("934847281", mode="subscribe", platform="discord")
            if not subs:
                self.call_from_thread(
                    self._add_system_message,
                    "[yellow]No Discord channels subscribed. Use /subscribe in Telegram.[/yellow]"
                )
                return
            channel_ids = [s["target_id"] for s in subs]
            channel_names = {s["target_id"]: s.get("target_name", s["target_id"]) for s in subs}
            messages = get_platform_messages("discord", channel_ids, hours=hours)
            if not messages:
                self.call_from_thread(
                    self._add_system_message,
                    f"[dim]No Discord messages in the last {hours}h.[/dim]"
                )
                return
            from collections import defaultdict
            by_channel = defaultdict(list)
            for m in messages:
                by_channel[m["chat_id"]].append(m)
            chat_lines = []
            for cid, msgs in by_channel.items():
                name = channel_names.get(cid, cid)
                chat_lines.append(f"## #{name} ({len(msgs)} messages)")
                for m in msgs:
                    sender = m.get("sender_name") or m["user_id"]
                    chat_lines.append(f"{sender}: {m['content']}")
                chat_lines.append("")
            chat_text = "\n".join(chat_lines)
            if len(chat_text) > 30000:
                chat_text = chat_text[:30000]
            total = len(messages)
            prompt = (
                f"Analyze Discord messages ({total} msgs, {len(by_channel)} channels, last {hours}h):\n\n"
                f"{chat_text}\n\nDigest each channel separately. Markdown."
            )
            result = _invoke_claude_streaming(
                prompt, on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context=f"[Discord digest: {hours}h]"
            )
            text = result.get("text", "No analysis.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(text, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="discord")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]Discord digest failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    @work(thread=True)
    def _run_whatsapp_digest(self, arg: str) -> None:
        """WhatsApp group digest from platform_messages."""
        self.is_streaming = True
        self.call_from_thread(self._update_status_bar)
        hours = 24
        try:
            from gateway.session_db import get_platform_messages, get_subscriptions, get_serve_targets
            subs = get_subscriptions("934847281", mode="subscribe", platform="whatsapp")
            serves = get_serve_targets("whatsapp")
            all_ids = {s["target_id"] for s in subs} | {t["target_id"] for t in serves}
            all_names = {}
            for s in subs:
                all_names[s["target_id"]] = s.get("target_name", s["target_id"])
            for t in serves:
                all_names[t["target_id"]] = t.get("target_name", t["target_id"])
            if not all_ids:
                self.call_from_thread(
                    self._add_system_message,
                    "[yellow]No WhatsApp groups subscribed/served.[/yellow]"
                )
                return
            messages = get_platform_messages("whatsapp", list(all_ids), hours=hours)
            if not messages:
                self.call_from_thread(
                    self._add_system_message,
                    f"[dim]No WhatsApp messages in the last {hours}h.[/dim]"
                )
                return
            from collections import defaultdict
            by_group = defaultdict(list)
            for m in messages:
                by_group[m["chat_id"]].append(m)
            chat_lines = []
            for gid, msgs in by_group.items():
                name = all_names.get(gid, gid)
                chat_lines.append(f"## {name} ({len(msgs)} messages)")
                for m in msgs:
                    sender = m.get("sender_name") or m["user_id"].split("@")[0]
                    chat_lines.append(f"{sender}: {m['content']}")
                chat_lines.append("")
            chat_text = "\n".join(chat_lines)
            if len(chat_text) > 30000:
                chat_text = chat_text[:30000]
            total = len(messages)
            prompt = (
                f"Analyze WhatsApp group messages ({total} msgs, {len(by_group)} groups, last {hours}h):\n\n"
                f"{chat_text}\n\nDigest each group separately. Markdown."
            )
            result = _invoke_claude_streaming(
                prompt, on_progress=lambda m: self.call_from_thread(
                    self._add_system_message, f"[dim]  {m}[/dim]"),
                model=self._state.model,
                session_context=f"[WhatsApp digest: {hours}h]"
            )
            text = result.get("text", "No analysis.")
            cost = result.get("cost", 0.0)
            self._state.add_assistant_message(text, cost)
            self.call_from_thread(self.post_message, CommandOutput(text, is_markdown=True))
            if cost > 0:
                log_cost(cost, platform="cli", session_id=self._state.session_id, pipeline="whatsapp")
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]WhatsApp digest failed: {e}[/red]")
        finally:
            self.is_streaming = False
            self.call_from_thread(self._update_status_bar)

    # ── /lang — language preference ─────────────────────────────

    def _cmd_lang(self, arg: str) -> None:
        """Set or view preferred output language."""
        user_id = "934847281"  # Vincent's Telegram user ID (canonical)

        if not arg:
            current = get_user_pref(user_id, "lang") or "en"
            name = LANG_NAMES.get(current, current)
            codes = ", ".join(f"`{k}`" for k in sorted(LANG_NAMES))
            self.post_message(CommandOutput(
                f"**Language**\n"
                f"- Current: {name} (`{current}`)\n\n"
                f"**Set:** `/lang <code>`\n"
                f"Codes: {codes}\n\n"
                f"**Reset:** `/lang reset` or `/lang off`",
                is_markdown=True,
            ))
            return

        code = arg.strip().lower()
        if code in ("reset", "off"):
            delete_user_pref(user_id, "lang")
            self._add_system_message("[green]Language reset to English.[/green]")
            return

        set_user_pref(user_id, "lang", code)
        name = LANG_NAMES.get(code, code)
        self._add_system_message(f"[green]Output language set to: {name} ({code})[/green]")

    # ── /do — natural language → command ────────────────────────

    def _cmd_do(self, arg: str) -> None:
        """Parse natural language into a slash command, then execute it."""
        if not arg:
            self.post_message(CommandOutput(
                "**Usage:** `/do <natural language instruction>`\n\n"
                "**Options:** `--preview` — show parsed command without running it\n\n"
                "**Examples:**\n"
                "- `/do absorb this repo https://github.com/foo/bar`\n"
                "- `/do learn about htmx`\n"
                "- `/do --preview search for memory management`\n"
                "- `/do show me the cost so far`\n",
                is_markdown=True,
            ))
            return
        self._run_do(arg)

    @work(thread=True)
    def _run_do(self, text: str) -> None:
        """Background worker: parse intent via haiku, then dispatch."""
        preview = False
        if "--preview" in text or "--dry-run" in text:
            preview = True
            text = text.replace("--preview", "").replace("--dry-run", "").strip()

        self.call_from_thread(self._add_system_message, "[dim]Parsing intent...[/dim]")

        try:
            proc = subprocess.run(
                [
                    "claude", "-p", "--model", "haiku",
                    "--no-chrome", "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
                    (
                        "You are a command parser. The user sent a natural language message to an AI agent system.\n"
                        "Your job: determine if this message maps to one of the available commands below.\n\n"
                        f"{_COMMAND_SCHEMA}\n"
                        "Rules:\n"
                        "- If the message clearly maps to a command, return the exact command string.\n"
                        "- If the message is general chat/question NOT related to any command, return null.\n"
                        "- Preserve URLs and arguments exactly as the user provided them.\n"
                        "- Map synonyms: 'study'/'research'/'dive into' -> /learn, 'integrate'/'absorb'/'steal from' -> /absorb, "
                        "'scan'/'evolve'/'find new tools' -> /evolve, 'find'/'search for' -> /search\n"
                        "- Map flags from natural language: 'skip security' -> --skip-security-scan, 'preview'/'dry run' -> --dry-run\n\n"
                        "Return ONLY a JSON object, nothing else:\n"
                        '{"command": "/absorb https://...", "confidence": 0.95}\n'
                        "or\n"
                        '{"command": null, "confidence": 0.0}\n\n'
                        f"User message: {text}"
                    ),
                ],
                capture_output=True, text=True, timeout=30,
            )

            if proc.returncode != 0:
                self.call_from_thread(
                    self._add_system_message,
                    "[red]Intent parsing failed (claude returned non-zero).[/red]"
                )
                return

            output = proc.stdout.strip()
            start = output.find("{")
            end = output.rfind("}") + 1
            if start < 0 or end <= start:
                self.call_from_thread(
                    self._add_system_message,
                    "[yellow]Couldn't map that to a known command. Try rephrasing, or use a command directly.[/yellow]"
                )
                return

            import json as _json
            parsed = _json.loads(output[start:end])
            cmd = parsed.get("command")
            confidence = parsed.get("confidence", 0)

            if not cmd or confidence < 0.7:
                self.call_from_thread(
                    self._add_system_message,
                    "[yellow]Couldn't map that to a known command (low confidence). Try rephrasing.[/yellow]"
                )
                return

            if preview:
                self.call_from_thread(
                    self.post_message,
                    CommandOutput(
                        f"**Preview (not executed):**\n`{cmd}` (confidence: {confidence:.0%})\n\n"
                        f"Run `/do {text}` without --preview to execute.",
                        is_markdown=True,
                    )
                )
                return

            self.call_from_thread(
                self._add_system_message,
                f"[dim]Parsed: {cmd} (confidence: {confidence:.0%}) — running...[/dim]"
            )
            # Dispatch the parsed command on the main thread
            self.call_from_thread(self._handle_command, cmd)

        except subprocess.TimeoutExpired:
            self.call_from_thread(
                self._add_system_message, "[red]Intent parsing timed out.[/red]"
            )
        except Exception as e:
            self.call_from_thread(
                self._add_system_message, f"[red]Intent parsing error: {e}[/red]"
            )

    # ── /restart — restart the gateway ──────────────────────────

    def _cmd_restart(self) -> None:
        """Restart the gateway process."""
        my_pid = os.getpid()
        exodir = str(EXODIR)
        restart_sh = Path("/tmp/ae-restart.sh")
        restart_sh.write_text(
            "#!/bin/bash\n"
            "sleep 2\n"
            f"kill {my_pid} 2>/dev/null\n"
            "sleep 1\n"
            f"kill -9 {my_pid} 2>/dev/null\n"
            "sleep 1\n"
            f"cd {exodir}\n"
            "nohup python3 -m gateway.run > /dev/null 2>&1 &\n"
        )
        restart_sh.chmod(0o755)
        subprocess.Popen(
            [str(restart_sh)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._add_system_message("[yellow]Restarting gateway in 2s... TUI will close.[/yellow]")
        # Give user a moment to see the message, then exit
        import threading as _threading
        def _exit_delayed():
            time.sleep(1)
            os._exit(0)
        _threading.Thread(target=_exit_delayed, daemon=True).start()

    # ── /speak — text-to-speech ─────────────────────────────────

    def _cmd_speak(self, arg: str) -> None:
        """Convert text to speech and play locally."""
        if not arg:
            self.post_message(CommandOutput(
                "**Usage:** `/speak <text>`\n\n"
                "**Options:**\n"
                "- `/speak --voices [lang]` — list available edge-tts voices\n"
                "- `/speak <text>` — convert text to speech and play via afplay\n",
                is_markdown=True,
            ))
            return
        self._run_speak(arg)

    @work(thread=True)
    def _run_speak(self, arg: str) -> None:
        """Background worker: TTS via edge-tts, then play with afplay."""
        import asyncio as _asyncio

        # /speak --voices [lang]
        parts = arg.split()
        if parts[0] in ("--voices", "--list"):
            lang = parts[1] if len(parts) > 1 else "en"
            try:
                from gateway.voice import list_voices
                loop = _asyncio.new_event_loop()
                voices = loop.run_until_complete(list_voices(lang))
                loop.close()
                if not voices:
                    self.call_from_thread(self._add_system_message, "[yellow]No voices found.[/yellow]")
                    return
                lines = [f"Edge TTS voices ({lang}):"]
                for v in voices[:30]:
                    name = v.get("ShortName", "?")
                    gender = v.get("Gender", "?")
                    lines.append(f"  {name} ({gender})")
                if len(voices) > 30:
                    lines.append(f"  ... and {len(voices) - 30} more")
                self.call_from_thread(self._add_system_message, "\n".join(lines))
            except Exception as e:
                self.call_from_thread(self._add_system_message, f"[red]Voice list failed: {e}[/red]")
            return

        # Generate TTS
        self.call_from_thread(self._add_system_message, "[dim]Generating speech...[/dim]")
        try:
            from gateway.voice import text_to_speech
            loop = _asyncio.new_event_loop()
            audio_path = loop.run_until_complete(text_to_speech(arg, output_format="mp3"))
            loop.close()

            if not audio_path or not audio_path.exists():
                self.call_from_thread(self._add_system_message, "[red]TTS produced no audio.[/red]")
                return

            self.call_from_thread(
                self._add_system_message,
                f"[green]Playing audio ({audio_path.stat().st_size // 1024}KB)...[/green]"
            )
            # Play with afplay (macOS)
            subprocess.run(["afplay", str(audio_path)], timeout=120)
            self.call_from_thread(self._add_system_message, "[dim]Playback complete.[/dim]")

        except Exception as e:
            self.call_from_thread(self._add_system_message, f"[red]TTS failed: {e}[/red]")

    # ── /subscribe — manage digest subscriptions ────────────────

    def _cmd_subscribe(self, arg: str) -> None:
        """View or manage digest subscriptions."""
        user_id = "934847281"
        self._cmd_subscription_common(arg, user_id, mode="subscribe")

    # ── /serve — manage serve targets ───────────────────────────

    def _cmd_serve(self, arg: str) -> None:
        """View or manage serve targets."""
        user_id = "934847281"
        self._cmd_subscription_common(arg, user_id, mode="serve")

    def _cmd_subscription_common(self, arg: str, user_id: str, mode: str) -> None:
        """Shared logic for /subscribe and /serve."""
        label = "Subscriptions" if mode == "subscribe" else "Serve targets"
        verb = "subscribe" if mode == "subscribe" else "serve"

        parts = arg.strip().split() if arg.strip() else []

        # /subscribe add <platform> <target_id> [name]
        if len(parts) >= 3 and parts[0] == "add":
            platform = parts[1].lower()
            target_id = parts[2]
            target_name = " ".join(parts[3:]) if len(parts) > 3 else target_id
            is_new = add_subscription(user_id, platform, target_id, target_name, "channel", mode)
            if is_new:
                self._add_system_message(
                    f"[green]Added {verb}: {platform} — {target_name}[/green]"
                )
                # Hot-reload serve targets if in serve mode
                if mode == "serve":
                    self._reload_serve_targets(platform)
            else:
                self._add_system_message(f"[yellow]Already {verb}d: {platform} — {target_name}[/yellow]")
            return

        # /subscribe remove <platform> <target_id>
        if len(parts) >= 3 and parts[0] in ("remove", "rm", "delete"):
            platform = parts[1].lower()
            target_id = parts[2]
            removed = remove_subscription(user_id, platform, target_id, mode)
            if removed:
                self._add_system_message(f"[green]Removed {verb}: {platform} — {target_id}[/green]")
                if mode == "serve":
                    self._reload_serve_targets(platform)
            else:
                self._add_system_message(f"[yellow]Not found: {platform} — {target_id}[/yellow]")
            return

        # /subscribe clear [platform]
        if parts and parts[0] == "clear":
            platform = parts[1].lower() if len(parts) > 1 else None
            subs = get_subscriptions(user_id, mode=mode, platform=platform)
            count = 0
            for s in subs:
                remove_subscription(user_id, s["platform"], s["target_id"], mode)
                count += 1
            self._add_system_message(f"[green]Cleared {count} {verb} target(s).[/green]")
            if mode == "serve":
                for p in {s["platform"] for s in subs}:
                    self._reload_serve_targets(p)
            return

        # Default: show current subscriptions
        subs = get_subscriptions(user_id, mode=mode)
        if not subs:
            self.post_message(CommandOutput(
                f"**{label}**\n\nNo {verb} targets configured.\n\n"
                f"**Add:** `/{verb} add <platform> <target_id> [name]`\n"
                f"**Remove:** `/{verb} remove <platform> <target_id>`\n"
                f"**Clear:** `/{verb} clear [platform]`",
                is_markdown=True,
            ))
            return

        lines = [f"**{label}**\n"]
        by_platform: dict[str, list] = {}
        for s in subs:
            by_platform.setdefault(s["platform"], []).append(s)
        for platform, items in sorted(by_platform.items()):
            lines.append(f"**{platform.title()}:**")
            for s in items:
                lines.append(f"  - {s['target_name']} (`{s['target_id']}`, {s['target_type']})")
        lines.append(f"\n**Add:** `/{verb} add <platform> <target_id> [name]`")
        lines.append(f"**Remove:** `/{verb} remove <platform> <target_id>`")
        self.post_message(CommandOutput("\n".join(lines), is_markdown=True))

    def _reload_serve_targets(self, platform: str) -> None:
        """Attempt to hot-reload serve targets for a platform adapter."""
        try:
            from gateway.run import GatewayRunner
            # If a running gateway instance exists, update its serve targets
            # This is best-effort — may not work if gateway is separate process
            import importlib
            mod = importlib.import_module(f"gateway.platforms.{platform}")
            if hasattr(mod, "_update_serve_targets"):
                mod._update_serve_targets(platform)
        except Exception:
            pass  # Best-effort: gateway may be a separate process


# ── Entry Point ─────────────────────────────────────────────────

def main(resume_session: str = None):
    """Launch the TUI."""
    app = AEApp(resume_session=resume_session)
    app.run()


if __name__ == "__main__":
    main()
