"""Tests for the enhanced hook system (Phase 3)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from gateway.hooks import HookRunner


class TestHookRunner:
    def setup_method(self):
        self.runner = HookRunner()

    @pytest.mark.asyncio
    async def test_void_hook_fires(self):
        listener = AsyncMock()
        self.runner.register("message_received", listener)
        await self.runner.fire_void("message_received",
                                    platform="telegram", text="hi")
        listener.assert_called_once_with(platform="telegram", text="hi")

    @pytest.mark.asyncio
    async def test_modifying_hook_mutates(self):
        async def uppercase(payload):
            return payload.upper()
        self.runner.register("before_invoke", uppercase, modifying=True)
        result = await self.runner.fire_modifying("before_invoke", "hello")
        assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_modifying_chain(self):
        async def add_prefix(payload):
            return f"[PREFIX] {payload}"
        async def add_suffix(payload):
            return f"{payload} [SUFFIX]"
        self.runner.register("before_invoke", add_prefix, modifying=True, priority=10)
        self.runner.register("before_invoke", add_suffix, modifying=True, priority=5)
        result = await self.runner.fire_modifying("before_invoke", "hello")
        # Higher priority fires first
        assert result == "[PREFIX] hello [SUFFIX]"

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        order = []
        async def first(**kwargs):
            order.append(1)
        async def second(**kwargs):
            order.append(2)
        async def third(**kwargs):
            order.append(3)
        # Register in reverse order, but with priorities
        self.runner.register("llm_output", third, priority=1)
        self.runner.register("llm_output", first, priority=10)
        self.runner.register("llm_output", second, priority=5)
        await self.runner.fire_void("llm_output", session_id="s1", text="x", cost=0)
        # Note: void hooks fire concurrently, so order isn't guaranteed by priority
        # But all should have been called
        assert sorted(order) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_modifying_priority_ordering(self):
        """Modifying hooks run sequentially in priority order."""
        order = []
        async def first(payload):
            order.append(1)
            return f"{payload}A"
        async def second(payload):
            order.append(2)
            return f"{payload}B"
        self.runner.register("before_invoke", first, modifying=True, priority=10)
        self.runner.register("before_invoke", second, modifying=True, priority=5)
        result = await self.runner.fire_modifying("before_invoke", "")
        assert order == [1, 2]
        assert result == "AB"

    @pytest.mark.asyncio
    async def test_void_exception_doesnt_crash(self):
        async def bad_listener(**kwargs):
            raise ValueError("boom")
        listener = AsyncMock()
        self.runner.register("message_received", bad_listener, priority=10)
        self.runner.register("message_received", listener, priority=5)
        await self.runner.fire_void("message_received", platform="t", text="hi")
        # Second listener should still be called (concurrent)
        listener.assert_called_once()

    @pytest.mark.asyncio
    async def test_modifying_exception_skipped(self):
        async def bad_listener(payload):
            raise ValueError("boom")
        async def good_listener(payload):
            return payload + " modified"
        self.runner.register("before_invoke", bad_listener, modifying=True, priority=10)
        self.runner.register("before_invoke", good_listener, modifying=True, priority=5)
        result = await self.runner.fire_modifying("before_invoke", "hello")
        assert result == "hello modified"

    def test_has_hooks(self):
        assert not self.runner.has_hooks("message_received")
        self.runner.register("message_received", AsyncMock())
        assert self.runner.has_hooks("message_received")

    def test_unregister(self):
        fn = AsyncMock()
        self.runner.register("message_received", fn)
        assert self.runner.has_hooks("message_received")
        removed = self.runner.unregister("message_received", fn)
        assert removed
        assert not self.runner.has_hooks("message_received")

    def test_unregister_not_found(self):
        fn = AsyncMock()
        removed = self.runner.unregister("message_received", fn)
        assert not removed

    def test_listener_count(self):
        self.runner.register("llm_output", AsyncMock())
        self.runner.register("llm_output", AsyncMock())
        self.runner.register("llm_output", AsyncMock(), modifying=True)
        assert self.runner.listener_count("llm_output") == 3

    def test_registered_hooks(self):
        self.runner.register("message_received", AsyncMock())
        self.runner.register("llm_output", AsyncMock())
        self.runner.register("llm_output", AsyncMock())
        result = self.runner.registered_hooks()
        assert result["message_received"] == 1
        assert result["llm_output"] == 2

    @pytest.mark.asyncio
    async def test_merge_fn(self):
        """Test modifying hook with custom merge function."""
        async def override(payload):
            return {"model": "opus"}
        def merge(old, new):
            if new.get("model"):
                return new
            return old
        self.runner.register("before_model_resolve", override, modifying=True)
        result = await self.runner.fire_modifying(
            "before_model_resolve", {"model": "sonnet"}, merge_fn=merge)
        assert result == {"model": "opus"}

    @pytest.mark.asyncio
    async def test_no_listeners_noop(self):
        """Fire with no listeners should be a no-op."""
        await self.runner.fire_void("message_received", text="hello")
        result = await self.runner.fire_modifying("before_invoke", "hello")
        assert result == "hello"

    def test_all_hook_points_defined(self):
        """All hook points in HOOK_POINTS should be strings."""
        assert len(self.runner.HOOK_POINTS) >= 19
        for hp in self.runner.HOOK_POINTS:
            assert isinstance(hp, str)
            assert "_" in hp or hp.isalpha()
