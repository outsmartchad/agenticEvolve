"""Shared SessionState for CLI and TUI interfaces."""
from gateway.agent import generate_title
from gateway.session_db import (
    generate_session_id,
    create_session,
    add_message,
    end_session,
    set_title,
    log_cost,
)


class SessionState:
    """Tracks the active chat session."""

    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "sonnet")
        self.session_id: str = ""
        self.history: list[dict] = []
        self.message_count: int = 0
        self.session_cost: float = 0.0
        self.workspace: str = ""  # project directory — empty = $HOME
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
