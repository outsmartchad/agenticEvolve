"""Tests for the event bus system (Phase 4)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from gateway.event_bus import EventBus, event_bus


class TestEventBus:
    def setup_method(self):
        self.bus = EventBus()

    # ── Registration ────────────────────────────────────────────

    def test_register_handler(self):
        handler = AsyncMock()
        self.bus.on("test:event", handler)
        assert self.bus.handler_count("test:event") == 1

    def test_register_multiple_handlers(self):
        h1 = AsyncMock()
        h2 = AsyncMock()
        self.bus.on("test:event", h1)
        self.bus.on("test:event", h2)
        assert self.bus.handler_count("test:event") == 2

    def test_register_different_events(self):
        h1 = AsyncMock()
        h2 = AsyncMock()
        self.bus.on("event:a", h1)
        self.bus.on("event:b", h2)
        assert self.bus.handler_count("event:a") == 1
        assert self.bus.handler_count("event:b") == 1

    # ── Unregistration ──────────────────────────────────────────

    def test_unregister_handler(self):
        handler = AsyncMock()
        self.bus.on("test:event", handler)
        assert self.bus.handler_count("test:event") == 1
        self.bus.off("test:event", handler)
        assert self.bus.handler_count("test:event") == 0

    def test_unregister_nonexistent_handler(self):
        """Unregistering a handler that was never registered doesn't crash."""
        handler = AsyncMock()
        self.bus.off("test:event", handler)  # should be a no-op
        assert self.bus.handler_count("test:event") == 0

    def test_unregister_only_removes_target(self):
        h1 = AsyncMock()
        h2 = AsyncMock()
        self.bus.on("test:event", h1)
        self.bus.on("test:event", h2)
        self.bus.off("test:event", h1)
        assert self.bus.handler_count("test:event") == 1

    # ── Emit ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_emit_calls_handler(self):
        called_with = {}

        async def handler(event_type, data):
            called_with["event_type"] = event_type
            called_with["data"] = data

        self.bus.on("test:event", handler)
        await self.bus.emit("test:event", foo="bar")
        assert called_with["event_type"] == "test:event"
        assert called_with["data"]["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_emit_calls_multiple_handlers(self):
        call_count = [0]

        async def h1(event_type, data):
            call_count[0] += 1

        async def h2(event_type, data):
            call_count[0] += 1

        self.bus.on("test:event", h1)
        self.bus.on("test:event", h2)
        await self.bus.emit("test:event")
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_emit_no_handlers_doesnt_crash(self):
        """Emitting with no handlers should be a no-op."""
        await self.bus.emit("nonexistent:event", data="test")

    @pytest.mark.asyncio
    async def test_emit_with_no_kwargs(self):
        received = {}

        async def handler(event_type, data):
            received["data"] = data

        self.bus.on("test:event", handler)
        await self.bus.emit("test:event")
        assert received["data"] == {}

    # ── Async handler ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_async_handler_awaited(self):
        result = []

        async def slow_handler(event_type, data):
            await asyncio.sleep(0.01)
            result.append("done")

        self.bus.on("test:event", slow_handler)
        await self.bus.emit("test:event")
        assert result == ["done"]

    # ── Sync handler ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sync_handler_works(self):
        """Non-coroutine handlers should also work."""
        result = []

        def sync_handler(event_type, data):
            result.append(event_type)

        self.bus.on("test:event", sync_handler)
        await self.bus.emit("test:event")
        assert result == ["test:event"]

    # ── Error handling ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_error_in_handler_doesnt_crash_bus(self):
        """An exception in one handler shouldn't prevent others from running."""
        result = []

        async def bad_handler(event_type, data):
            raise ValueError("boom")

        async def good_handler(event_type, data):
            result.append("ok")

        self.bus.on("test:event", bad_handler)
        self.bus.on("test:event", good_handler)
        await self.bus.emit("test:event")
        assert result == ["ok"]

    @pytest.mark.asyncio
    async def test_error_in_sync_handler_doesnt_crash(self):
        result = []

        def bad_handler(event_type, data):
            raise RuntimeError("sync boom")

        async def good_handler(event_type, data):
            result.append("ok")

        self.bus.on("test:event", bad_handler)
        self.bus.on("test:event", good_handler)
        await self.bus.emit("test:event")
        assert result == ["ok"]

    # ── Introspection ───────────────────────────────────────────

    def test_handler_count_empty(self):
        assert self.bus.handler_count("nonexistent") == 0

    def test_registered_events(self):
        self.bus.on("event:a", AsyncMock())
        self.bus.on("event:b", AsyncMock())
        events = self.bus.registered_events()
        assert "event:a" in events
        assert "event:b" in events

    def test_registered_events_empty(self):
        assert self.bus.registered_events() == []

    # ── Global singleton ────────────────────────────────────────

    def test_global_singleton_exists(self):
        assert event_bus is not None
        assert isinstance(event_bus, EventBus)

    # ── emit_sync ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_emit_sync_schedules_task(self):
        """emit_sync should schedule the emit on the running loop."""
        result = []

        async def handler(event_type, data):
            result.append("fired")

        self.bus.on("test:event", handler)
        self.bus.emit_sync("test:event")
        # Give the task a chance to run
        await asyncio.sleep(0.05)
        assert result == ["fired"]
