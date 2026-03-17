"""Tests for gateway.debounce — message debouncing."""
import asyncio

import pytest

from gateway.debounce import MessageDebouncer


@pytest.mark.asyncio
async def test_single_message_delivered():
    """Single message should be delivered after window."""
    results = []
    d = MessageDebouncer(window_seconds=0.1)

    async def cb(text):
        results.append(text)

    d.enqueue("k1", "hello", cb)
    await asyncio.sleep(0.3)
    assert results == ["hello"]


@pytest.mark.asyncio
async def test_multiple_messages_batched():
    """Rapid messages should be batched into one delivery."""
    results = []
    d = MessageDebouncer(window_seconds=0.2)

    async def cb(text):
        results.append(text)

    d.enqueue("k1", "msg1", cb)
    d.enqueue("k1", "msg2", cb)
    d.enqueue("k1", "msg3", cb)
    await asyncio.sleep(0.5)
    assert len(results) == 1
    assert "msg1" in results[0]
    assert "msg2" in results[0]
    assert "msg3" in results[0]


@pytest.mark.asyncio
async def test_different_keys_independent():
    """Different keys should debounce independently."""
    results = []
    d = MessageDebouncer(window_seconds=0.1)

    async def cb(text):
        results.append(text)

    d.enqueue("k1", "a", cb)
    d.enqueue("k2", "b", cb)
    await asyncio.sleep(0.3)
    assert len(results) == 2
    assert "a" in results
    assert "b" in results


@pytest.mark.asyncio
async def test_max_wait_forces_delivery():
    """max_wait should force delivery even if messages keep arriving."""
    results = []
    d = MessageDebouncer(window_seconds=0.5, max_wait=0.3)

    async def cb(text):
        results.append(text)

    d.enqueue("k1", "msg1", cb)
    await asyncio.sleep(0.15)
    d.enqueue("k1", "msg2", cb)
    await asyncio.sleep(0.15)
    d.enqueue("k1", "msg3", cb)
    await asyncio.sleep(0.5)
    # Should have delivered at least once due to max_wait
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_pending_count():
    d = MessageDebouncer(window_seconds=0.5)

    async def cb(text):
        pass

    assert d.pending_count() == 0
    d.enqueue("k1", "hi", cb)
    assert d.pending_count() == 1
    assert d.is_pending("k1") is True
    assert d.is_pending("k2") is False
    await asyncio.sleep(0.7)
    assert d.pending_count() == 0
