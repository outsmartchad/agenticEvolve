"""Base platform adapter interface."""
from abc import ABC, abstractmethod
from typing import Callable, Awaitable


class BasePlatformAdapter(ABC):
    """All platform adapters must implement this interface."""

    def __init__(self, config: dict, on_message: Callable):
        self.config = config
        self.on_message = on_message  # async callback(platform, chat_id, user_id, text) -> str

    @abstractmethod
    async def start(self):
        """Connect to the platform and start listening."""
        ...

    @abstractmethod
    async def stop(self):
        """Disconnect gracefully."""
        ...

    @abstractmethod
    async def send(self, chat_id: str, text: str):
        """Send a message to a specific chat."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform name (telegram, discord, whatsapp)."""
        ...
