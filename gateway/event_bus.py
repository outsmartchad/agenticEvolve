"""Lightweight in-process event bus for reactive triggers."""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any

log = logging.getLogger("agenticEvolve.event_bus")


class EventBus:
    """Simple pub/sub event bus. Handlers are async callables."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event_type: str, handler: Callable):
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        log.debug(f"Event handler registered: {event_type} -> {handler.__name__}")

    def off(self, event_type: str, handler: Callable):
        """Unregister a handler."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def emit(self, event_type: str, **data):
        """Emit an event. All handlers run sequentially with error isolation."""
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return
        log.debug(f"Event emitted: {event_type} ({len(handlers)} handlers)")
        for handler in handlers:
            try:
                result = handler(event_type, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.error(f"Event handler error ({event_type}): {e}")

    def emit_sync(self, event_type: str, **data):
        """Emit from sync context -- schedules on the running loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event_type, **data))
        except RuntimeError:
            pass  # no event loop running

    def handler_count(self, event_type: str) -> int:
        """Return number of handlers registered for an event type."""
        return len(self._handlers.get(event_type, []))

    def registered_events(self) -> list[str]:
        """Return list of event types that have handlers."""
        return [k for k, v in self._handlers.items() if v]


# Global singleton
event_bus = EventBus()
