"""Inbound message debouncing (OpenClaw pattern).

When a user sends multiple rapid-fire messages (common in WhatsApp/Telegram),
this collects them into a single batch before invoking the LLM. Prevents
wasted API calls on partial messages.

Usage:
    debouncer = MessageDebouncer(window_seconds=2.5)

    # Returns immediately. Callback fires after debounce window.
    debouncer.enqueue(key, text, callback)

    # If another message arrives within the window, the timer resets
    # and the new text is appended to the batch.
"""
import asyncio
import logging
from collections import defaultdict

log = logging.getLogger("agenticEvolve.debounce")


class MessageDebouncer:
    """Collects rapid-fire messages into batches per session key."""

    def __init__(self, window_seconds: float = 2.5, max_wait: float = 8.0):
        """
        Args:
            window_seconds: Debounce window — resets on each new message.
            max_wait: Maximum total wait time before forcing delivery,
                      even if messages keep arriving.
        """
        self.window = window_seconds
        self.max_wait = max_wait
        # key -> list of pending text chunks
        self._buffers: dict[str, list[str]] = defaultdict(list)
        # key -> current debounce timer task
        self._timers: dict[str, asyncio.Task] = {}
        # key -> first message timestamp (for max_wait enforcement)
        self._first_ts: dict[str, float] = {}
        # key -> callback + args to fire when debounce window closes
        self._callbacks: dict[str, tuple] = {}

    def enqueue(self, key: str, text: str,
                callback, *args, **kwargs) -> None:
        """Add a message to the debounce buffer.

        Args:
            key: Session key (e.g. "whatsapp:chat_id:user_id")
            text: Message text
            callback: Async function to call with batched text when window closes
            *args, **kwargs: Additional args passed to callback
        """
        loop = asyncio.get_event_loop()
        now = loop.time()

        self._buffers[key].append(text)
        self._callbacks[key] = (callback, args, kwargs)

        # Track first message time for max_wait
        if key not in self._first_ts:
            self._first_ts[key] = now

        # Cancel existing timer
        if key in self._timers:
            self._timers[key].cancel()

        # Check if we've exceeded max_wait
        elapsed = now - self._first_ts.get(key, now)
        if elapsed >= self.max_wait:
            # Force delivery now
            log.debug(f"Debounce: max_wait reached for {key}, forcing delivery")
            self._timers[key] = asyncio.ensure_future(self._deliver(key))
        else:
            # Set new timer
            remaining_max = self.max_wait - elapsed
            wait = min(self.window, remaining_max)
            self._timers[key] = asyncio.ensure_future(
                self._delayed_deliver(key, wait))

    async def _delayed_deliver(self, key: str, delay: float):
        """Wait for debounce window then deliver."""
        try:
            await asyncio.sleep(delay)
            await self._deliver(key)
        except asyncio.CancelledError:
            pass  # Timer was reset by a new message

    async def _deliver(self, key: str):
        """Deliver the batched messages."""
        chunks = self._buffers.pop(key, [])
        self._timers.pop(key, None)
        self._first_ts.pop(key, None)
        cb_info = self._callbacks.pop(key, None)

        if not chunks or not cb_info:
            return

        callback, args, kwargs = cb_info

        # Join multiple messages with newlines
        if len(chunks) == 1:
            batched_text = chunks[0]
        else:
            batched_text = "\n".join(chunks)
            log.info(f"Debounce: batched {len(chunks)} messages for {key}")

        try:
            await callback(batched_text, *args, **kwargs)
        except Exception as e:
            log.error(f"Debounce delivery error for {key}: {e}")

    def pending_count(self) -> int:
        """Number of keys with pending debounced messages."""
        return len(self._buffers)

    def is_pending(self, key: str) -> bool:
        """Check if a key has pending debounced messages."""
        return key in self._buffers
